"""Ciclo de ejecución, inyección/limpieza de flags y validación de retos."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core import get_current_user, get_settings, now_utc, require_roles, submission_fingerprint, verify_password
from ..models import (
    Challenge, ChallengeCompletion, ChallengeGroupAssignment, ChallengeInstance, ChallengeRun, ChallengeRunFlag,
    GroupMembership, Laboratory, RemoteAccessAssignment, StudentGroup, Submission, User, VMAsset,
)

from ..schemas import RunView, SubmissionRequest, SubmissionResponse
from ..services.bootstrap import check_rate_limit, ranking_rows, write_audit
from ..services.challenge_runtime import _find_challenge_vm, _resolve_guacamole_connection
from ..services.dynamic_flags import DynamicFlagRuntime
from ..services.lab_lock import (
    LabReservationBusy, LabReservationError, LabReservationUnavailable,
    acquire, release, reserve_for_cleanup,
)
from ..services.runtime_flags import is_effectively_dynamic
from ..domain.instances.states import InstanceState


router = APIRouter()
logger = logging.getLogger(__name__)
ATTACK_CHALLENGE_CODE = "ESC-01-RECON"


def _player_launch_url(challenge: Challenge, assignment: RemoteAccessAssignment | None, *, player: bool = True) -> str | None:
    # El acceso a ESC se emite únicamente mediante el ticket de Kali del puente
    # WebSocket; la conexión SSH de la víctima es solo para la API/inyector.
    return assignment.launch_url if assignment and player and challenge.code != ATTACK_CHALLENGE_CODE else None


def _view_from_run(run: ChallengeRun, challenge: Challenge, assignment: RemoteAccessAssignment | None, vm=None, protocol: str | None = None, *, player: bool = True) -> RunView:
    return RunView(
        id=run.id,
        challenge_code=challenge.code,
        status=run.status,
        started_at=run.started_at,
        expires_at=run.expires_at,
        launch_url=_player_launch_url(challenge, assignment, player=player),
        connection_state=assignment.status if assignment else None,
        workspace_strategy=run.workspace_strategy,
        target_vm_name=vm.name if vm else None,
        target_vm_ip=vm.ip_address if vm else None,
        target_protocol=protocol,
        laboratory_code=None,
    )


async def _assigned(session, challenge_id: int, user_id: int) -> bool:
    found = await session.scalar(
        select(ChallengeGroupAssignment.id)
        .join(GroupMembership, GroupMembership.group_id == ChallengeGroupAssignment.group_id)
        .join(StudentGroup, StudentGroup.id == GroupMembership.group_id)
        .where(
            ChallengeGroupAssignment.challenge_id == challenge_id,
            GroupMembership.user_id == user_id,
            StudentGroup.is_active.is_(True),
        )
    )
    return found is not None


async def _connection_protocol(request: Request, identifier: str | None) -> str | None:
    if not identifier:
        return None
    try:
        connections = await request.app.state.guacamole_admin.list_connections()
    except Exception:
        return None
    item = next((row for row in connections if row.identifier == identifier), None)
    return item.protocol if item else None


async def _sync_player_guacamole_permissions(request: Request, user_id: int, connection_identifier: str) -> bool:
    """Garantiza que el usuario del laboratorio pueda usar la conexión asignada.

    Conserva permisos existentes, agrega READ sobre la conexión objetivo y
    devuelve si READ ya existía antes de la sincronización.
    No modifica PostgreSQL: la sincronización se realiza directamente en Guacamole.
    """
    async with request.app.state.session_factory() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise RuntimeError(f"Usuario CTF {user_id} no encontrado")

    permissions = await request.app.state.guacamole_admin.get_user_permissions(user.username)
    connection_permissions = {
        str(key): list(value or [])
        for key, value in (permissions.get("connectionPermissions") or {}).items()
    }
    current = set(connection_permissions.get(str(connection_identifier), []))
    preexisting = "READ" in current
    if preexisting:
        return True
    current.add("READ")
    connection_permissions[str(connection_identifier)] = sorted(current)

    await request.app.state.guacamole_admin.patch_user_permissions(
        user.username,
        system_permissions=list(permissions.get("systemPermissions") or []),
        connection_permissions=connection_permissions,
    )
    return preexisting


async def _remove_run_guacamole_permission(request: Request, username: str, connection_identifier: str) -> None:
    """Retira solo READ concedido por la ejecución y conserva los otros permisos."""
    permissions = await request.app.state.guacamole_admin.get_user_permissions(username)
    connection_permissions = {
        str(key): list(value or [])
        for key, value in (permissions.get("connectionPermissions") or {}).items()
    }
    current = set(connection_permissions.get(str(connection_identifier), []))
    if "READ" not in current:
        return
    current.discard("READ")
    if current:
        connection_permissions[str(connection_identifier)] = sorted(current)
    else:
        connection_permissions.pop(str(connection_identifier), None)
    await request.app.state.guacamole_admin.patch_user_permissions(
        username,
        system_permissions=list(permissions.get("systemPermissions") or []),
        connection_permissions=connection_permissions,
    )


def _return_instance_to_pool(instance: ChallengeInstance | None) -> None:
    if instance is None:
        return
    instance.state = InstanceState.AVAILABLE.value
    instance.run_id = None
    instance.user_id = None
    instance.reserved_at = None
    instance.expires_at = None
    instance.guacamole_access_granted = False
    instance.guacamole_access_preexisting = False
    instance.last_error = None


async def _cleanup_run(request: Request, session, run: ChallengeRun, challenge: Challenge | None, *, status: str):
    """Cierra una ejecución bajo lock de fila y protege la VM original de la reserva."""
    instance = await session.scalar(
        select(ChallengeInstance).where(ChallengeInstance.run_id == run.id).with_for_update()
    )
    if instance:
        target_vm = await session.get(VMAsset, instance.vm_asset_id)
        target_lab = await session.get(Laboratory, target_vm.laboratory_id) if target_vm else None
    else:
        target_lab, target_vm = await _find_challenge_vm(session, challenge) if challenge else (None, None)

    dynamic = bool(challenge and any(is_effectively_dynamic(challenge.code, flag) for flag in challenge.flags))
    if dynamic and target_vm and target_vm.ip_address:
        # Compatibilidad con ejecuciones anteriores a la fila de pool: no tocar
        # evidencia si esa VM ya fue asignada a una ejecución distinta.
        if instance is None:
            owner = await session.scalar(
                select(ChallengeInstance).where(ChallengeInstance.vm_asset_id == target_vm.id).with_for_update()
            )
            if owner and owner.run_id not in (None, run.id):
                raise HTTPException(status_code=409, detail="La instancia pertenece a otra ejecución")
        try:
            await reserve_for_cleanup(
                request.app.state.redis, target_vm.ip_address, run.id,
                get_settings().flag_injector_lock_ttl_seconds,
            )
        except LabReservationError as exc:
            raise HTTPException(status_code=503, detail="No se pudo reservar la instancia para su limpieza") from exc
    elif dynamic:
        raise HTTPException(status_code=503, detail="No se encontró la VM de la ejecución para limpiar la evidencia")

    try:
        terminal_sessions = getattr(request.app.state, "terminal_sessions", None)
        if terminal_sessions is not None:
            await terminal_sessions.close_run(run.id)
        if run.assignment:
            await request.app.state.guacamole.revoke(run.assignment.external_reference)
        if instance and instance.guacamole_access_granted and not instance.guacamole_access_preexisting and instance.guacamole_connection_id:
            owner_user = await session.get(User, run.user_id)
            if owner_user is None:
                raise RuntimeError("Usuario de la ejecución no disponible")
            await _remove_run_guacamole_permission(request, owner_user.username, instance.guacamole_connection_id)
        if dynamic:
            await DynamicFlagRuntime(request.app.state.flag_injector).cleanup(session, run.id, challenge, target_vm)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="No se pudo cerrar y limpiar el laboratorio. Vuelve a intentar el cierre.") from exc

    if dynamic and target_vm and target_vm.ip_address:
        # La fila del pool continúa bloqueada: otro inicio puede reservar Redis,
        # pero no puede reutilizar ni inyectar esta VM antes de nuestro commit.
        if not await release(request.app.state.redis, target_vm.ip_address, str(run.id)):
            raise HTTPException(status_code=503, detail="La evidencia fue limpiada, pero no se pudo liberar la reserva. Vuelve a intentar el cierre.")

    if run.assignment:
        run.assignment.status = "expired" if status == "expired" else "revoked"
    _return_instance_to_pool(instance)
    run.status = status
    run.closed_at = now_utc()
    await write_audit(session, run.user_id, "challenge_run.expire" if status == "expired" else "challenge_run.close", "challenge_run", str(run.id), {
        "challenge": challenge.code if challenge else None,
        "dynamic_cleanup": dynamic,
    })
    await session.commit()
    return target_lab, target_vm


async def expire_stale_runs(request: Request, *, batch_size: int = 25) -> dict[str, int]:
    """Limpieza periódica reutilizable; una VM inaccesible queda pendiente para reintento."""
    async with request.app.state.session_factory() as session:
        run_ids = list((await session.scalars(
            select(ChallengeRun.id)
            .where(ChallengeRun.status == "active", ChallengeRun.expires_at < now_utc())
            .order_by(ChallengeRun.expires_at).limit(batch_size)
        )).all())
    cleaned, pending = 0, 0
    for run_id in run_ids:
        async with request.app.state.session_factory() as session:
            run = await session.scalar(
                select(ChallengeRun).options(selectinload(ChallengeRun.assignment))
                .where(ChallengeRun.id == run_id).with_for_update()
            )
            if run is None or run.status != "active" or run.expires_at >= now_utc():
                continue
            challenge = await session.scalar(
                select(Challenge).options(selectinload(Challenge.flags)).where(Challenge.id == run.challenge_id)
            )
            try:
                await _cleanup_run(request, session, run, challenge, status="expired")
                cleaned += 1
            except Exception:
                await session.rollback()
                pending += 1
    return {"cleaned": cleaned, "pending": pending}


async def _rollback_failed_start(request: Request, session, *, username: str, connection_identifier: str | None,
                                 temporary_permission: bool, external_reference: str | None,
                                 lock_token: str | None, target_ip: str | None, target_os: str | None,
                                  injector: DynamicFlagRuntime, challenge_code: str, dynamic_flags: list, injection_started: bool) -> None:
    """Deshace solo recursos que este intento obtuvo, sin tocar una reserva ajena."""
    await session.rollback()
    cleaned = True
    if lock_token and injection_started:
        for flag in dynamic_flags:
            try:
                await request.app.state.flag_injector.clear(target_ip or "", injector.path_for(flag, challenge_code), target_os)
            except Exception:
                cleaned = False
    if external_reference:
        try:
            await request.app.state.guacamole.revoke(external_reference)
        except Exception:
            cleaned = False
    if temporary_permission and connection_identifier:
        try:
            await _remove_run_guacamole_permission(request, username, connection_identifier)
        except Exception:
            cleaned = False
    # Si la limpieza física falló se conserva el lock hasta su TTL; evita
    # reutilizar inmediatamente una VM que todavía puede contener evidencia.
    if lock_token and cleaned:
        if not await release(request.app.state.redis, target_ip or "", lock_token):
            logger.warning("Rollback de inicio: liberación Redis no confirmada; la reserva permanece hasta su TTL")


@router.post("/api/v1/challenges/{code}/start", response_model=RunView)
async def start_challenge(code: str, request: Request, user=Depends(require_roles("player"))):
    await check_rate_limit(request.app.state.redis, f"rate:start:{user.id}:{code}", maximum=6)
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(
            select(Challenge)
            .options(selectinload(Challenge.flags))
            .where(Challenge.code == code, Challenge.is_published.is_(True))
            .with_for_update()
        )
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no disponible")
        if not await _assigned(session, challenge.id, user.id):
            raise HTTPException(status_code=403, detail="Este reto no está asignado a tu grupo")

        now = now_utc()
        active_run = await session.scalar(
            select(ChallengeRun)
            .options(selectinload(ChallengeRun.assignment))
            .where(
                ChallengeRun.user_id == user.id,
                ChallengeRun.challenge_id == challenge.id,
                ChallengeRun.status == "active",
            )
            .order_by(ChallengeRun.id.desc())
            .with_for_update()
        )
        if active_run and active_run.expires_at >= now:
            instance = await session.scalar(select(ChallengeInstance).where(ChallengeInstance.run_id == active_run.id))
            if instance:
                target_vm = await session.get(VMAsset, instance.vm_asset_id)
                connection_identifier = instance.guacamole_connection_id
            else:
                _, target_vm = await _find_challenge_vm(session, challenge)
                connection_identifier = target_vm.guacamole_connection_id if target_vm else None
            protocol = await _connection_protocol(request, connection_identifier)
            return _view_from_run(active_run, challenge, active_run.assignment, target_vm, protocol)
        if active_run and active_run.expires_at < now:
            await _cleanup_run(request, session, active_run, challenge, status="expired")

        now = now_utc()

        dynamic_flags = [flag for flag in challenge.flags if is_effectively_dynamic(challenge.code, flag)]
        target_lab, target_vm = await _find_challenge_vm(session, challenge)
        if dynamic_flags and (target_vm is None or not target_vm.ip_address):
            raise HTTPException(status_code=409, detail="El reto dinámico requiere una VM víctima Linux con IP y conexión Guacamole")

        settings = get_settings()
        target_vm_ip = target_vm.ip_address if target_vm else None
        target_vm_os = target_vm.os if target_vm else None
        # Preflight Guacamole before taking the Redis reservation. This avoids
        # creating a lock that cannot be released when Guacamole is misconfigured.
        try:
            guac_connection = await _resolve_guacamole_connection(request, target_vm) if target_vm else None
        except Exception as exc:
            raise HTTPException(status_code=503, detail="No se pudo comprobar la conexión del laboratorio") from exc
        if dynamic_flags and target_vm and (guac_connection is None or (guac_connection.protocol or "").lower() != "ssh"):
            raise HTTPException(
                status_code=409,
                detail="El laboratorio todavía no tiene una conexión SSH disponible. Contacta al instructor.",
            )
        if dynamic_flags and target_vm:
            preflight = getattr(request.app.state.flag_injector, "preflight", None)
            if preflight is not None:
                try:
                    await preflight(target_vm.ip_address)
                except Exception as exc:
                    raise HTTPException(
                        status_code=503,
                        detail="La VM víctima no acepta SSH desde la API. Comprueba que esté encendida, en la red correcta y con SSH disponible.",
                    ) from exc
            probe_authentication = getattr(request.app.state.flag_injector, "probe_authentication", None)
            if probe_authentication is not None:
                try:
                    await probe_authentication(target_vm.ip_address)
                except Exception as exc:
                    raise HTTPException(
                        status_code=503,
                        detail="La API llega a la VM, pero la cuenta del inyector no puede autenticarse por SSH. Contacta al instructor.",
                    ) from exc

        # Garantiza que el estudiante tenga READ sobre la conexión concreta del laboratorio.
        # Esto evita que Guacamole abra otra conexión previamente asignada al usuario.
        guacamole_access_preexisting = False

        expires_at = now + timedelta(seconds=settings.flag_injector_lock_ttl_seconds)
        run = ChallengeRun(
            user_id=user.id,
            challenge_id=challenge.id,
            status="active",
            expires_at=expires_at,
            workspace_strategy="shared_lab_vm",
        )
        session.add(run)
        await session.flush()

        lock_token: str | None = None
        injection_started = False
        temporary_permission = False
        external_reference: str | None = None
        provisioned_reference: str | None = None
        username = user.username
        connection_identifier = str(guac_connection.identifier) if guac_connection else None
        injector = DynamicFlagRuntime(request.app.state.flag_injector)
        stage = "reservation"
        try:
            if dynamic_flags:
                # La plantilla se valida antes de reservar la VM: una ruta
                # inválida no debe dejar un lock Redis ni tocar evidencia.
                for flag in dynamic_flags:
                    injector.path_for(flag, challenge.code)
                lock_token = await acquire(
                    request.app.state.redis,
                    target_vm.ip_address,
                    run.id,
                    ttl_seconds=settings.flag_injector_lock_ttl_seconds,
                )

            stage = "remote_access"
            target_url: str
            target_protocol: str | None = None
            laboratory_code = target_lab.code if target_lab else None
            if target_vm and guac_connection:
                try:
                    if challenge.code == ATTACK_CHALLENGE_CODE:
                        # Columna existente NOT NULL: guardar un destino inocuo,
                        # nunca el enlace directo a la víctima.
                        target_url = f"{settings.guacamole_base_url.rstrip('/')}/#/home"
                    else:
                        target_url = await request.app.state.guacamole.direct_connection_url(guac_connection.identifier)
                        target_protocol = guac_connection.protocol
                    external_reference = f"vm:{target_vm.id}:connection:{guac_connection.identifier}:run:{run.id}"
                except RuntimeError as exc:
                    raise HTTPException(status_code=503, detail="No se pudo preparar el acceso al laboratorio") from exc
            else:
                try:
                    remote = await request.app.state.guacamole.provision(user.username, challenge.code, run.id)
                    target_url = remote.launch_url
                    external_reference = remote.external_reference
                    provisioned_reference = remote.external_reference
                except RuntimeError as exc:
                    raise HTTPException(status_code=503, detail="No se pudo preparar el acceso al laboratorio") from exc

            assignment = RemoteAccessAssignment(
                run_id=run.id,
                external_reference=external_reference,
                launch_url=target_url,
                expires_at=expires_at,
            )
            session.add(assignment)

            stage = "instance_pool"
            if dynamic_flags and target_vm:
                # ChallengeInstance representa una fila de pool por VM.
                # La restricción uq_challenge_instance_vm_asset impide crear otra
                # fila para la misma VM, por lo que primero reutilizamos la existente.
                instance = await session.scalar(
                    select(ChallengeInstance)
                    .where(ChallengeInstance.vm_asset_id == target_vm.id)
                    .with_for_update()
                )

                if instance is None:
                    instance = ChallengeInstance(
                        challenge_id=challenge.id,
                        vm_asset_id=target_vm.id,
                        run_id=run.id,
                        user_id=user.id,
                        state=InstanceState.IN_USE.value,
                        ip_address=target_vm.ip_address,
                        guacamole_connection_id=str(guac_connection.identifier) if guac_connection else None,
                        guacamole_access_granted=False,
                        guacamole_access_preexisting=False,
                        reserved_at=now,
                        expires_at=expires_at,
                        last_error=None,
                    )
                    session.add(instance)
                else:
                    # La instancia existente debe estar libre después de una
                    # ejecución anterior o de una limpieza por expiración.
                    if (
                        instance.state != InstanceState.AVAILABLE.value
                        or instance.run_id is not None
                        or instance.user_id is not None
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="La instancia sigue marcada en uso. Cierra la ejecución anterior o pide al instructor verificar su limpieza.",
                        )

                    instance.challenge_id = challenge.id
                    instance.run_id = run.id
                    instance.user_id = user.id
                    instance.state = InstanceState.IN_USE.value
                    instance.ip_address = target_vm.ip_address
                    instance.guacamole_connection_id = (
                        str(guac_connection.identifier) if guac_connection else None
                    )
                    instance.guacamole_access_granted = False
                    instance.guacamole_access_preexisting = False
                    instance.reserved_at = now
                    instance.expires_at = expires_at
                    instance.last_error = None

                await session.flush()

                # ESC inyecta en la víctima, pero el alumno trabaja desde Kali.
                # Nunca conceder READ de la conexión víctima por esta corrida.
                if challenge.code != ATTACK_CHALLENGE_CODE:
                    stage = "guacamole_permissions"
                    guacamole_access_preexisting = await _sync_player_guacamole_permissions(
                        request, user.id, guac_connection.identifier
                    )
                    temporary_permission = not guacamole_access_preexisting
                    instance.guacamole_access_granted = True
                    instance.guacamole_access_preexisting = guacamole_access_preexisting

            stage = "flag_injection"
            if dynamic_flags:
                injection_started = True
                # Elimina restos del mismo archivo antes de escribir la nueva evidencia.
                for flag in dynamic_flags:
                    try:
                        await request.app.state.flag_injector.clear(target_vm_ip or "", injector.path_for(flag, challenge.code), target_vm_os)
                    except Exception:
                        # La escritura posterior sustituirá un archivo existente de forma atómica.
                        pass
                await injector.prepare(session, challenge, run, username, target_vm)

            stage = "database_commit"
            await write_audit(session, user.id, "challenge_run.start", "challenge_run", str(run.id), {
                "challenge": code,
                "remote_reference": external_reference,
                "target_vm": target_vm.name if target_vm else None,
                "target_laboratory": laboratory_code,
                "workspace_strategy": run.workspace_strategy,
                "dynamic_flag_count": len(dynamic_flags),
            })
            await session.commit()

            return RunView(
                id=run.id,
                challenge_code=challenge.code,
                status=run.status,
                started_at=run.started_at,
                expires_at=expires_at,
                launch_url=_player_launch_url(challenge, assignment),
                connection_state="ready",
                workspace_strategy=run.workspace_strategy,
                target_vm_name=target_vm.name if target_vm else None,
                target_vm_ip=target_vm.ip_address if target_vm else None,
                target_protocol=target_protocol,
                laboratory_code=laboratory_code,
            )
        except HTTPException:
            await _rollback_failed_start(request, session, username=username, connection_identifier=connection_identifier,
                temporary_permission=temporary_permission, external_reference=provisioned_reference,
                lock_token=lock_token, target_ip=target_vm_ip, target_os=target_vm_os,
                injector=injector, challenge_code=challenge.code, dynamic_flags=dynamic_flags, injection_started=injection_started)
            raise
        except (ValueError, LabReservationError, RuntimeError) as exc:
            logger.warning("Inicio de laboratorio fallido: etapa=%s tipo=%s", stage, type(exc).__name__)
            await _rollback_failed_start(request, session, username=username, connection_identifier=connection_identifier,
                temporary_permission=temporary_permission, external_reference=provisioned_reference,
                lock_token=lock_token, target_ip=target_vm_ip, target_os=target_vm_os,
                injector=injector, challenge_code=challenge.code, dynamic_flags=dynamic_flags, injection_started=injection_started)
            if isinstance(exc, LabReservationBusy):
                # No revelar la cuenta o el ID de la ejecución que ocupa la VM.
                raise HTTPException(status_code=409,
                    detail="La VM del reto está reservada por otra ejecución. Espera a que termine o pide al instructor verificar su cierre.") from exc
            if isinstance(exc, LabReservationUnavailable):
                raise HTTPException(status_code=503,
                    detail="No se pudo comprobar la reserva del laboratorio. Vuelve a intentar cuando Redis esté disponible.") from exc
            if isinstance(exc, ValueError):
                raise HTTPException(status_code=409,
                    detail="La configuración de la flag del reto necesita revisión del instructor.") from exc
            if stage == "guacamole_permissions":
                raise HTTPException(status_code=503,
                    detail="No se pudieron preparar los permisos de Guacamole para tu cuenta. Contacta al instructor.") from exc
            if stage == "flag_injection":
                raise HTTPException(status_code=503,
                    detail="No se pudo escribir la flag en la VM. El instructor debe comprobar el acceso SSH del inyector y el script remoto.") from exc
            raise HTTPException(status_code=503,
                detail="No se pudo preparar el laboratorio. Verifica que la VM y el servicio de acceso estén disponibles o contacta al instructor.") from exc
        except Exception as exc:
            logger.warning("Inicio de laboratorio fallido: etapa=%s tipo=%s", stage, type(exc).__name__)
            await _rollback_failed_start(request, session, username=username, connection_identifier=connection_identifier,
                temporary_permission=temporary_permission, external_reference=provisioned_reference,
                lock_token=lock_token, target_ip=target_vm_ip, target_os=target_vm_os,
                injector=injector, challenge_code=challenge.code, dynamic_flags=dynamic_flags, injection_started=injection_started)
            raise HTTPException(status_code=500, detail="No se pudo preparar el entorno del reto") from exc


@router.get("/api/v1/runs", response_model=list[RunView])
async def list_runs(request: Request, user=Depends(get_current_user)):
    async with request.app.state.session_factory() as session:
        statement = (
            select(ChallengeRun, Challenge, RemoteAccessAssignment, ChallengeInstance, VMAsset)
            .join(Challenge, Challenge.id == ChallengeRun.challenge_id)
            .outerjoin(RemoteAccessAssignment, RemoteAccessAssignment.run_id == ChallengeRun.id)
            .outerjoin(ChallengeInstance, ChallengeInstance.run_id == ChallengeRun.id)
            .outerjoin(VMAsset, VMAsset.id == ChallengeInstance.vm_asset_id)
        )
        if user.role == "player":
            assigned_challenges = (
                select(ChallengeGroupAssignment.challenge_id)
                .join(GroupMembership, GroupMembership.group_id == ChallengeGroupAssignment.group_id)
                .join(StudentGroup, StudentGroup.id == GroupMembership.group_id)
                .where(GroupMembership.user_id == user.id, StudentGroup.is_active.is_(True))
            )
            statement = statement.where(
                ChallengeRun.user_id == user.id,
                Challenge.is_published.is_(True),
                Challenge.id.in_(assigned_challenges),
            )
        elif user.role not in ("admin", "instructor"):
            return []
        statement = statement.order_by(ChallengeRun.started_at.desc()).limit(30)
        rows = (await session.execute(statement)).all()
        current = now_utc()
        response: list[RunView] = []
        for run, challenge, assignment, instance, vm in rows:
            state = "expired" if run.status == "active" and run.expires_at < current else run.status

            # Las ejecuciones históricas creadas antes de ChallengeInstance
            # también deben poder mostrarse en la interfaz. Resolvemos la VM
            # de forma no mutante cuando el registro de instancia todavía no existe.
            display_vm = vm
            display_protocol = None
            if display_vm is None and challenge and state == "active":
                _, display_vm = await _find_challenge_vm(session, challenge)

            if instance and instance.guacamole_connection_id:
                display_protocol = await _connection_protocol(request, instance.guacamole_connection_id)
            elif display_vm:
                resolved_connection = await _resolve_guacamole_connection(request, display_vm)
                display_protocol = resolved_connection.protocol if resolved_connection else None

            response.append(
                RunView(
                    id=run.id,
                    challenge_code=challenge.code,
                    status=state,
                    started_at=run.started_at,
                    expires_at=run.expires_at,
                    launch_url=_player_launch_url(challenge, assignment, player=user.role == "player"),
                    connection_state=assignment.status if assignment else None,
                    workspace_strategy=run.workspace_strategy,
                    target_vm_name=display_vm.name if display_vm else None,
                    target_vm_ip=display_vm.ip_address if display_vm else None,
                    target_protocol=display_protocol,
                    laboratory_code=None,
                )
            )
        return response


@router.post("/api/v1/runs/{run_id}/close", response_model=RunView)
async def close_run(run_id: int, request: Request, user=Depends(require_roles("player"))):
    async with request.app.state.session_factory() as session:
        run = await session.scalar(
            select(ChallengeRun)
            .options(selectinload(ChallengeRun.assignment))
            .where(ChallengeRun.id == run_id, ChallengeRun.user_id == user.id)
            .with_for_update()
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Ejecución no encontrada")
        challenge = await session.scalar(select(Challenge).options(selectinload(Challenge.flags)).where(Challenge.id == run.challenge_id))
        if run.status in ("closed", "expired"):
            return RunView(id=run.id, challenge_code=challenge.code if challenge else "", status=run.status, started_at=run.started_at, expires_at=run.expires_at, launch_url=None, connection_state=run.assignment.status if run.assignment else None, workspace_strategy=run.workspace_strategy)
        target_lab, target_vm = await _cleanup_run(request, session, run, challenge, status="closed")
        return RunView(id=run.id, challenge_code=challenge.code if challenge else "", status=run.status, started_at=run.started_at, expires_at=run.expires_at, launch_url=None, connection_state=run.assignment.status if run.assignment else None, workspace_strategy=run.workspace_strategy, target_vm_name=target_vm.name if target_vm else None, target_vm_ip=target_vm.ip_address if target_vm else None, laboratory_code=target_lab.code if target_lab else None)


@router.post("/api/v1/challenges/{code}/submissions", response_model=SubmissionResponse)
async def submit_flag(code: str, payload: SubmissionRequest, request: Request, user=Depends(require_roles("player"))):
    await check_rate_limit(request.app.state.redis, f"rate:flag:{user.id}:{code}", maximum=8)
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(select(Challenge).options(selectinload(Challenge.flags)).where(Challenge.code == code, Challenge.is_published.is_(True)))
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no disponible")
        if not await _assigned(session, challenge.id, user.id):
            raise HTTPException(status_code=403, detail="Este reto no está asignado a tu grupo")
        flags = [item for item in challenge.flags if item.is_active]
        if not flags:
            raise HTTPException(status_code=409, detail="El reto todavía no está configurado con flags activas")
        run = await session.scalar(select(ChallengeRun).where(ChallengeRun.user_id == user.id, ChallengeRun.challenge_id == challenge.id, ChallengeRun.status == "active").order_by(ChallengeRun.id.desc()).with_for_update())
        if run is None or run.expires_at < now_utc():
            raise HTTPException(status_code=409, detail="Debes iniciar el reto antes de enviar la flag")

        matched = None
        for flag in flags:
            if is_effectively_dynamic(challenge.code, flag):
                run_flag = await session.scalar(select(ChallengeRunFlag).where(ChallengeRunFlag.run_id == run.id, ChallengeRunFlag.flag_id == flag.id))
                if run_flag and verify_password(payload.value, run_flag.flag_hash):
                    matched = flag
                    break
            elif flag.flag_hash and verify_password(payload.value, flag.flag_hash):
                matched = flag
                break

        submission = Submission(
            user_id=user.id,
            challenge_id=challenge.id,
            flag_id=matched.id if matched else None,
            submitted_value_hmac=submission_fingerprint(payload.value),
            is_correct=matched is not None,
        )
        session.add(submission)
        awarded_points, complete = 0, False
        if matched:
            correct_ids = set((await session.scalars(select(Submission.flag_id).where(Submission.user_id == user.id, Submission.challenge_id == challenge.id, Submission.is_correct.is_(True)))).all())
            correct_ids.add(matched.id)
            if {item.id for item in flags}.issubset(correct_ids):
                completion = await session.scalar(select(ChallengeCompletion).where(ChallengeCompletion.user_id == user.id, ChallengeCompletion.challenge_id == challenge.id))
                complete = True
                if completion is None:
                    completion = ChallengeCompletion(user_id=user.id, challenge_id=challenge.id, awarded_points=challenge.points)
                    session.add(completion)
                    awarded_points, complete = challenge.points, True
                    await write_audit(session, user.id, "challenge.complete", "challenge", str(challenge.id), {"code": code, "points": challenge.points})
        await session.commit()

    if complete:
        if awarded_points:
            rows = await ranking_rows(request.app.state.session_factory)
            payload_event = {"type": "ranking.updated", "rows": rows}
            await request.app.state.sockets.broadcast(payload_event)
            try:
                await request.app.state.redis.publish("ctf:ranking", __import__("json").dumps(payload_event))
            except Exception:
                pass
        message = ("Flag correcta. Reto completado; cierra la sesión del laboratorio para limpiar la VM."
                   if awarded_points else "Flag correcta. Este reto ya estaba completado; puedes cerrar el laboratorio para limpiar la VM.")
        return SubmissionResponse(correct=True, challenge_completed=True, awarded_points=awarded_points, message=message)
    if matched:
        return SubmissionResponse(correct=True, challenge_completed=False, awarded_points=0, message="Flag correcta. Continúa con las flags restantes.")
    return SubmissionResponse(correct=False, challenge_completed=False, awarded_points=0, message="Flag incorrecta. Revisa el escenario e inténtalo de nuevo.")
