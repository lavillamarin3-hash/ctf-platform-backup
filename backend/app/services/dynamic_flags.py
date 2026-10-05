"""Orquestación de flags dinámicas sin acoplar el dominio a SSH o PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy import select

from ..core import get_settings, hash_password, submission_fingerprint
from ..domain.flags.service import FlagService
from ..domain.ports.flag_injector import FlagInjectorGateway
from ..models import Challenge, ChallengeFlag, ChallengeRun, ChallengeRunFlag, VMAsset
from .runtime_flags import effective_mode_template, is_effectively_dynamic


@dataclass(frozen=True)
class PreparedDynamicFlag:
    """Metadatos mínimos que se necesitan para limpiar la evidencia."""

    flag_id: int
    order: int
    path: str


class DynamicFlagRuntime:
    """Genera, persiste por hash, inyecta y limpia flags de una ejecución."""

    def __init__(self, injector: FlagInjectorGateway, flag_service: FlagService | None = None) -> None:
        self.injector = injector
        self.flags = flag_service or FlagService()
        self.settings = get_settings()

    def path_for(self, flag: ChallengeFlag, challenge_code: str) -> str:
        # Este escenario comparte VM con LAB-01, pero nunca su archivo de flag.
        # LAB-01 conserva la ruta heredada para no alterar corridas existentes.
        template = (
            "/opt/ctf/ESC-01-RECON/flag.txt"
            if challenge_code == "ESC-01-RECON"
            else self.settings.flag_injector_flag_path
        )
        if "{{CODE}}" in template:
            if not re.fullmatch(r"[A-Z0-9-]{3,64}", challenge_code):
                raise ValueError("El código del reto no es válido para una ruta de flag")
            template = template.replace("{{CODE}}", challenge_code)
        path = template.replace("{{ORDER}}", str(flag.flag_order))
        if (not path.startswith("/opt/ctf/") or path.endswith("/")
                or any(part in ("", ".", "..") for part in path.split("/")[3:])
                or "{{" in path or "}}" in path or any(ord(char) < 32 for char in path)):
            raise ValueError("FLAG_INJECTOR_FLAG_PATH debe apuntar a un archivo dentro de /opt/ctf")
        return path

    async def prepare(
        self,
        session,
        challenge: Challenge,
        run: ChallengeRun,
        username: str,
        target_vm: VMAsset | None,
    ) -> list[PreparedDynamicFlag]:
        dynamic_flags = [flag for flag in challenge.flags if is_effectively_dynamic(challenge.code, flag)]
        if not dynamic_flags:
            return []
        if target_vm is None or not target_vm.ip_address:
            raise ValueError("El reto dinámico necesita una VM víctima con IP asignada")
        if not self.settings.flag_injector_enabled:
            raise ValueError("El inyector SSH está deshabilitado; activa FLAG_INJECTOR_ENABLED para un reto dinámico")
        if challenge.code == "ESC-01-RECON" and len(dynamic_flags) > 1:
            raise ValueError("ESC-01-RECON admite una sola flag dinámica de evidencia")
        if len(dynamic_flags) > 1 and "{{ORDER}}" not in self.settings.flag_injector_flag_path:
            raise ValueError("Hay varias flags dinámicas activas. Usa FLAG_INJECTOR_FLAG_PATH con {{ORDER}} para darles archivos distintos")

        prepared: list[PreparedDynamicFlag] = []
        for flag in sorted(dynamic_flags, key=lambda item: item.flag_order):
            path = self.path_for(flag, challenge.code)
            _mode, template = effective_mode_template(challenge.code, flag)
            if not template:
                raise ValueError(f"La flag dinámica {flag.label or flag.id} no tiene plantilla efectiva")
            clear_value = self.flags.render_template(
                template,
                code=challenge.code,
                username=username,
                run_id=run.id,
            )
            await self.injector.inject(target_vm.ip_address, path, clear_value, target_vm.os)
            session.add(
                ChallengeRunFlag(
                    run_id=run.id,
                    flag_id=flag.id,
                    flag_hash=hash_password(clear_value),
                    fingerprint=submission_fingerprint(clear_value),
                )
            )
            prepared.append(PreparedDynamicFlag(flag_id=flag.id, order=flag.flag_order, path=path))
        return prepared

    async def cleanup(
        self,
        session,
        run_id: int,
        challenge: Challenge,
        target_vm: VMAsset | None,
    ) -> None:
        """Limpia únicamente las rutas de flags dinámicas usadas por la ejecución."""
        if target_vm is None or not target_vm.ip_address:
            return
        dynamic_ids = {
            flag.id: flag
            for flag in challenge.flags
            if is_effectively_dynamic(challenge.code, flag)
        }
        if not dynamic_ids:
            return
        # Limpia por las rutas efectivas, no solo por las filas ChallengeRunFlag.
        # Es necesario para recuperarse de una inyección parcial seguida de rollback.
        for flag in sorted(dynamic_ids.values(), key=lambda item: item.flag_order):
            await self.injector.clear(target_vm.ip_address, self.path_for(flag, challenge.code), target_vm.os)
