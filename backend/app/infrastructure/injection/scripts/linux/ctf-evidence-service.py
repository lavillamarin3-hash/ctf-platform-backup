#!/usr/bin/env python3
"""Servicio didáctico independiente para ESC-01-RECON en LNX-VICT.

Instalación manual solamente. No lo inicia la API ni se publica el reto por
añadir este archivo. Escucha en la IP de la víctima y sirve únicamente la flag
dinámica que ya haya inyectado el backend en
/opt/ctf/ESC-01-RECON/flag.txt. No comparte la flag de LAB-01.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import stat


class EvidenceHandler(BaseHTTPRequestHandler):
    allowed_client_ip = "192.168.146.134"
    flag_path = Path("/opt/ctf/ESC-01-RECON/flag.txt")

    def log_message(self, _format: str, *_args: object) -> None:
        # Ni la ruta ni la flag ni las cabeceras se escriben en stdout/stderr.
        pass

    def _reply(self, status: int, content: bytes, *, head_only: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def _read_evidence(self) -> bytes | None:
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.flag_path, flags)
            with os.fdopen(descriptor, "rb") as flag_file:
                if not stat.S_ISREG(os.fstat(flag_file.fileno()).st_mode):
                    return None
                content = flag_file.read(513)
            if not content or len(content) > 512:
                return None
            return content
        except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
            return None

    def _handle(self, *, head_only: bool = False) -> None:
        if self.client_address[0] != self.allowed_client_ip:
            self._reply(403, b"Acceso restringido al laboratorio\n", head_only=head_only)
        elif self.path == "/":
            self._reply(200, b"Servicio de evidencia. Consulta /evidence\n", head_only=head_only)
        elif self.path in ("/evidence", "/evidencia"):
            evidence = self._read_evidence()
            if evidence is None:
                self._reply(404, b"Evidencia no disponible\n", head_only=head_only)
            else:
                self._reply(200, evidence, head_only=head_only)
        else:
            self._reply(404, b"Ruta no encontrada\n", head_only=head_only)

    def do_GET(self) -> None:
        self._handle()

    def do_HEAD(self) -> None:
        self._handle(head_only=True)


def main() -> None:
    server = ThreadingHTTPServer(("192.168.146.137", 18081), EvidenceHandler)
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
