"""Adaptador SSH para inyección controlada de banderas en Linux.

La conexión se configura exclusivamente mediante variables de entorno y
se apoya en un script remoto de permisos mínimos.
"""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

from ...core import get_settings

ESC_EVIDENCE_PATH = "/opt/ctf/ESC-01-RECON/flag.txt"


class FlagInjectionError(RuntimeError):
    """Error controlado al no poder confirmar una operación de inyección."""


class SSHFlagInjector:
    """Implementación concreta de ``FlagInjectorGateway`` para Linux."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.script = Path(__file__).with_name("scripts") / "linux" / "ctf-inject-flag.sh"

    async def preflight(self, ip: str) -> None:
        """Comprueba TCP/SSH antes de crear un run o reservar Redis, sin enviar credenciales."""
        if not ip or not self.settings.flag_injector_enabled:
            raise FlagInjectionError("La VM o el inyector SSH no están disponibles")
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, self.settings.flag_injector_ssh_port),
                timeout=self.settings.flag_injector_connect_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise FlagInjectionError("La VM no acepta SSH desde el contenedor API") from exc
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            # El servidor puede cerrar el socket mientras enviaba el banner.
            # El handshake TCP ya se completó; la autenticación real se hará después.
            pass

    async def probe_authentication(self, ip: str) -> None:
        """Comprueba credenciales del inyector con `true`; no escribe en la VM."""
        await asyncio.to_thread(self._run_sync, ip, "", None, clear=False, probe_auth=True)

    async def inject(self, ip: str, path: str, value: str, os_type: str) -> None:
        """Conecta por SSH y ejecuta únicamente el script remoto permitido."""
        normalized_os = os_type.lower()
        if not ("linux" in normalized_os or "ubuntu" in normalized_os):
            raise FlagInjectionError("SSHFlagInjector solo admite sistemas Linux/Ubuntu")
        if not ip:
            raise FlagInjectionError("La VM destino no tiene una IP")
        if not self.settings.flag_injector_enabled:
            raise FlagInjectionError("El inyector SSH está deshabilitado en la configuración")
        if not path.startswith("/opt/ctf/"):
            raise FlagInjectionError("La ruta de la flag debe permanecer dentro de /opt/ctf")
        if not value.strip():
            raise FlagInjectionError("La bandera no puede estar vacía")
        await asyncio.to_thread(self._run_sync, ip, path, value, clear=False)

    async def clear(self, ip: str, path: str, os_type: str) -> None:
        """Elimina la flag de la VM al cerrar la ejecución."""
        normalized_os = os_type.lower()
        if not ("linux" in normalized_os or "ubuntu" in normalized_os):
            raise FlagInjectionError("SSHFlagInjector solo admite sistemas Linux/Ubuntu")
        if not ip:
            raise FlagInjectionError("La VM destino no tiene una IP")
        if not self.settings.flag_injector_enabled:
            raise FlagInjectionError("El inyector SSH está deshabilitado en la configuración")
        if not path.startswith("/opt/ctf/"):
            raise FlagInjectionError("La ruta de la flag debe permanecer dentro de /opt/ctf")
        await asyncio.to_thread(self._run_sync, ip, path, None, clear=True)

    def _run_sync(self, ip: str, path: str, value: str | None, *, clear: bool, probe_auth: bool = False) -> None:
        private_evidence = path == ESC_EVIDENCE_PATH and not clear and not probe_auth
        if private_evidence and (
            not value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or len(value.encode("utf-8")) > 511
        ):
            raise FlagInjectionError("La evidencia de ESC debe ser una línea corta sin caracteres de control")
        try:
            import paramiko
        except ImportError as exc:  # pragma: no cover - depende de la imagen de backend
            raise FlagInjectionError("Falta la dependencia paramiko en el backend") from exc

        client = paramiko.SSHClient()
        try:
            if self.settings.flag_injector_known_hosts:
                client.load_host_keys(self.settings.flag_injector_known_hosts)
            else:
                client.load_system_host_keys()

            if self.settings.flag_injector_strict_host_key:
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": ip,
                "port": self.settings.flag_injector_ssh_port,
                "username": self.settings.flag_injector_ssh_user,
                "timeout": self.settings.flag_injector_connect_timeout,
                "banner_timeout": self.settings.flag_injector_connect_timeout,
                "auth_timeout": self.settings.flag_injector_connect_timeout,
                "allow_agent": False,
                "look_for_keys": False,
            }
            if self.settings.flag_injector_ssh_private_key:
                connect_kwargs["key_filename"] = self.settings.flag_injector_ssh_private_key
            elif self.settings.flag_injector_ssh_password:
                connect_kwargs["password"] = self.settings.flag_injector_ssh_password
            else:
                raise FlagInjectionError("Configure una clave privada o contraseña SSH para el inyector")

            client.connect(**connect_kwargs)
            if probe_auth:
                _, stdout, _ = client.exec_command("true", timeout=self.settings.flag_injector_command_timeout)
                if stdout.channel.recv_exit_status() != 0:
                    raise FlagInjectionError("La cuenta del inyector no pudo ejecutar una comprobación de solo lectura")
                return
            if clear:
                remote_command = (
                    f"sudo -n {shlex.quote(self.settings.flag_injector_remote_script)} "
                    f"--path {shlex.quote(path)} --clear"
                )
            elif private_evidence:
                remote_command = (
                    f"sudo -n {shlex.quote(self.settings.flag_injector_remote_script)} "
                    f"--path {shlex.quote(path)} --stdin"
                )
            else:
                remote_command = (
                    f"sudo -n {shlex.quote(self.settings.flag_injector_remote_script)} "
                    f"--path {shlex.quote(path)} --flag {shlex.quote(value or '')}"
                )
            stdin, stdout, stderr = client.exec_command(remote_command, timeout=self.settings.flag_injector_command_timeout)
            if private_evidence:
                # Paramiko envía la evidencia por el canal cifrado y luego EOF.
                # El comando remoto, sus argumentos y los errores nunca la contienen.
                stdin.write(value + "\n")
                stdin.flush()
                stdin.channel.shutdown_write()
            exit_code = stdout.channel.recv_exit_status()
            error_text = stderr.read().decode("utf-8", errors="replace").strip()
            if exit_code != 0:
                safe_detail = (
                    "El script remoto no confirmó la inyección de evidencia"
                    if private_evidence
                    else error_text or f"El script remoto devolvió código {exit_code}"
                )
                raise FlagInjectionError(safe_detail)
        except FlagInjectionError:
            raise
        except Exception as exc:
            if private_evidence:
                raise FlagInjectionError("No se pudo inyectar la evidencia por SSH") from None
            raise FlagInjectionError(f"No se pudo conectar o ejecutar la operación SSH en {ip}: {exc}") from exc
        finally:
            client.close()
