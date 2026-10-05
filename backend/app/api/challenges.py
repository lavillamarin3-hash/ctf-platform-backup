"""Catálogo de retos, categorías y configuración de flags."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from ..core import get_current_user, hash_password, require_roles
from ..models import Challenge, ChallengeCompletion, ChallengeFlag, ChallengeGroupAssignment, ChallengeRun, GroupMembership, StudentGroup, User
from ..schemas import ChallengeCreate, ChallengeView, FlagCreate, FlagUpdate
from ..services.bootstrap import challenge_view, write_audit
from ..services.runtime_flags import EXPLICIT_STATIC_VALIDATOR, is_effectively_dynamic


from fastapi import APIRouter

router = APIRouter()


async def require_idle_challenge(session, challenge_id: int) -> None:
    """No altera evidencia/configuración mientras haya corridas por limpiar."""
    running = await session.scalar(select(ChallengeRun.id).where(
        ChallengeRun.challenge_id == challenge_id, ChallengeRun.status == "active",
    ).limit(1))
    if running is not None:
        raise HTTPException(409, "Cierra y limpia las corridas activas antes de cambiar los activos o las flags del reto.")

@router.get("/api/v1/challenges", response_model=list[ChallengeView])
async def list_challenges(request: Request, difficulty: str | None = None, category: str | None = None, mitre: str | None = None, user=Depends(get_current_user)):
    async with request.app.state.session_factory() as session:
        statement = select(Challenge).options(selectinload(Challenge.flags))
        if user.role not in ("admin", "instructor"):
            statement = statement.where(Challenge.is_published.is_(True))
            # Un reto para jugadores solo es visible si está asignado a uno de sus grupos.
            # Si no tiene asignaciones, se considera no publicado para estudiantes.
            assigned_exists = select(ChallengeGroupAssignment.id).join(
                GroupMembership, GroupMembership.group_id == ChallengeGroupAssignment.group_id
            ).join(
                StudentGroup, StudentGroup.id == GroupMembership.group_id
            ).where(
                ChallengeGroupAssignment.challenge_id == Challenge.id,
                GroupMembership.user_id == user.id,
                StudentGroup.is_active.is_(True),
            ).exists()
            statement = statement.where(assigned_exists)
        if difficulty:
            statement = statement.where(Challenge.difficulty == difficulty)
        if category:
            statement = statement.where(Challenge.category.ilike(category))
        if mitre:
            statement = statement.where(Challenge.mitre_technique.ilike(f"%{mitre}%"))
        statement = statement.order_by(Challenge.difficulty, Challenge.code)
        challenges = (await session.scalars(statement)).unique().all()
        completed_ids = set((await session.scalars(select(ChallengeCompletion.challenge_id).where(ChallengeCompletion.user_id == user.id))).all())
        include_flags = user.role in ("admin", "instructor")
        result = [challenge_view(item, item.id in completed_ids, include_flags) for item in challenges]
        if user.role == "guest":
            # El invitado conoce el catálogo, pero no obtiene instrucciones ni referencias de acceso.
            for item in result:
                item.instructions = "Acceso disponible únicamente para jugadores autorizados."
                item.asset_references = ["Información de acceso restringida"]
        return result


@router.get("/api/v1/categories")
async def list_categories(request: Request, user=Depends(get_current_user)):
    async with request.app.state.session_factory() as session:
        statement = select(Challenge.category, func.count(Challenge.id)).where(Challenge.is_published.is_(True)).group_by(Challenge.category).order_by(Challenge.category)
        if user.role not in ("admin", "instructor"):
            statement = statement.where(select(ChallengeGroupAssignment.id).join(
                GroupMembership, GroupMembership.group_id == ChallengeGroupAssignment.group_id,
            ).join(StudentGroup, StudentGroup.id == GroupMembership.group_id).where(
                ChallengeGroupAssignment.challenge_id == Challenge.id,
                GroupMembership.user_id == user.id, StudentGroup.is_active.is_(True),
            ).exists())
        rows = (await session.execute(statement)).all()
        return [{"name": name, "challenge_count": int(count)} for name, count in rows]


@router.post("/api/v1/challenges", response_model=ChallengeView, status_code=status.HTTP_201_CREATED)
async def create_challenge(payload: ChallengeCreate, request: Request, user=Depends(require_roles("admin", "instructor"))):
    async with request.app.state.session_factory() as session:
        if await session.scalar(select(Challenge).where(Challenge.code == payload.code)):
            raise HTTPException(status_code=409, detail="Ya existe un reto con ese código")
        challenge = Challenge(**payload.model_dump(), created_by=user.id)
        session.add(challenge)
        await session.flush()
        await write_audit(session, user.id, "challenge.create", "challenge", str(challenge.id), {"code": challenge.code})
        await session.commit()
        await session.refresh(challenge, attribute_names=["flags"])
        return challenge_view(challenge, include_flags=True)


@router.put("/api/v1/challenges/{code}", response_model=ChallengeView)
async def update_challenge(code: str, payload: ChallengeCreate, request: Request, user=Depends(require_roles("admin", "instructor"))):
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(select(Challenge).options(selectinload(Challenge.flags)).where(Challenge.code == code).with_for_update())
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no encontrado")
        if payload.code != challenge.code or payload.asset_references != challenge.asset_references:
            await require_idle_challenge(session, challenge.id)
        for field, value in payload.model_dump().items():
            setattr(challenge, field, value)
        await write_audit(session, user.id, "challenge.update", "challenge", str(challenge.id), {"code": code})
        await session.commit()
        await session.refresh(challenge, attribute_names=["flags"])
        return challenge_view(challenge, include_flags=True)


@router.delete("/api/v1/challenges/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_challenge(code: str, request: Request, user=Depends(require_roles("admin", "instructor"))):
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(select(Challenge).where(Challenge.code == code).with_for_update())
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no encontrado")
        # Despublicar una corrida en curso cortaría la terminal y dejaría la
        # evidencia dinámica pendiente. Exigir cierre/limpieza antes de archivar.
        await require_idle_challenge(session, challenge.id)
        challenge.is_published = False
        await write_audit(session, user.id, "challenge.archive", "challenge", str(challenge.id), {"code": code})
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/challenges/{code}/flags", response_model=ChallengeView)
async def create_flag(code: str, payload: FlagCreate, request: Request, user=Depends(require_roles("admin", "instructor"))):
    if payload.mode == "static" and not payload.value:
        raise HTTPException(status_code=422, detail="Una flag estática requiere un valor")
    if payload.mode == "dynamic" and not payload.template:
        raise HTTPException(status_code=422, detail="Una flag dinámica requiere una plantilla")
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(select(Challenge).options(selectinload(Challenge.flags)).where(Challenge.code == code).with_for_update())
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no encontrado")
        await require_idle_challenge(session, challenge.id)
        flag = ChallengeFlag(
            challenge_id=challenge.id,
            label=payload.label,
            flag_hash=hash_password(payload.value) if payload.mode == "static" and payload.value else None,
            validator=EXPLICIT_STATIC_VALIDATOR if payload.mode == "static" else "exact_hash",
            flag_order=payload.flag_order,
            is_active=True,
            mode=payload.mode,
            template=payload.template if payload.mode == "dynamic" else None,
        )
        session.add(flag)
        await write_audit(session, user.id, "flag.create", "challenge", str(challenge.id), {"order": payload.flag_order, "mode": payload.mode})
        await session.commit()
        await session.refresh(challenge, attribute_names=["flags"])
        return challenge_view(challenge, include_flags=True)


@router.put("/api/v1/challenges/{code}/flags/{flag_id}", response_model=ChallengeView)
async def update_flag(code: str, flag_id: int, payload: FlagUpdate, request: Request, user=Depends(require_roles("admin", "instructor"))):
    if payload.mode == "static" and payload.value == "":
        raise HTTPException(status_code=422, detail="Una flag estática requiere un valor")
    if payload.mode == "dynamic" and not payload.template:
        raise HTTPException(status_code=422, detail="Una flag dinámica requiere una plantilla")
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(select(Challenge).options(selectinload(Challenge.flags)).where(Challenge.code == code).with_for_update())
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no encontrado")
        flag = next((item for item in challenge.flags if item.id == flag_id), None)
        if flag is None:
            raise HTTPException(status_code=404, detail="Flag no encontrada")
        if payload.mode == "static" and payload.value is None and is_effectively_dynamic(code, flag):
            raise HTTPException(status_code=422, detail="Para cambiar una flag dinámica a estática debes ingresar su valor")
        changes_runtime = any((
            flag.flag_order != payload.flag_order, flag.is_active != payload.is_active,
            flag.mode != payload.mode, flag.template != (payload.template if payload.mode == "dynamic" else None),
            payload.mode == "static" and payload.value is not None,
        ))
        if changes_runtime:
            await require_idle_challenge(session, challenge.id)
        flag.label = payload.label
        flag.flag_order = payload.flag_order
        flag.is_active = payload.is_active
        flag.mode = payload.mode
        flag.template = payload.template if payload.mode == "dynamic" else None
        if payload.mode == "static" and payload.value is not None:
            flag.flag_hash = hash_password(payload.value)
            flag.validator = EXPLICIT_STATIC_VALIDATOR
        elif payload.mode == "dynamic":
            flag.flag_hash = None
            # Los hashes históricos pertenecen a su run; editar no los destruye.
        await write_audit(session, user.id, "flag.update", "flag", str(flag.id), {"challenge": code, "order": payload.flag_order, "mode": payload.mode, "active": payload.is_active})
        await session.commit()
        await session.refresh(challenge, attribute_names=["flags"])
        return challenge_view(challenge, include_flags=True)


@router.delete("/api/v1/challenges/{code}/flags/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flag(code: str, flag_id: int, request: Request, user=Depends(require_roles("admin", "instructor"))):
    async with request.app.state.session_factory() as session:
        challenge = await session.scalar(select(Challenge).where(Challenge.code == code).with_for_update())
        if challenge is None:
            raise HTTPException(status_code=404, detail="Reto no encontrado")
        await require_idle_challenge(session, challenge.id)
        flag = await session.get(ChallengeFlag, flag_id)
        if flag is None or flag.challenge_id != challenge.id:
            raise HTTPException(status_code=404, detail="Flag no encontrada")
        await write_audit(session, user.id, "flag.delete", "flag", str(flag.id), {"challenge": code})
        await session.delete(flag)
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


