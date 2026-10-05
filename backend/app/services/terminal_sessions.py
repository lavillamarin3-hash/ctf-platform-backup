"""Sesiones efímeras de terminal: tickets de un uso y secretos solo en backend."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets

from cryptography.fernet import Fernet, InvalidToken

from ..core import get_settings


class TerminalSessions:
    def __init__(self, redis_client):
        self.redis = redis_client
        key = hashlib.sha256(("ctf-terminal:" + get_settings().field_hmac_secret).encode()).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(key))
        self.connections: dict[int, set] = {}

    async def remember_user(self, user_id: int, delegated: dict) -> None:
        encrypted = self.cipher.encrypt(json.dumps(delegated).encode()).decode()
        await self.redis.set(
            f"ctf:terminal:user:{user_id}", encrypted,
            ex=get_settings().access_token_minutes * 60,
        )

    async def get_user(self, user_id: int) -> dict | None:
        encrypted = await self.redis.get(f"ctf:terminal:user:{user_id}")
        if not encrypted:
            return None
        try:
            return json.loads(self.cipher.decrypt(encrypted.encode()))
        except (InvalidToken, ValueError, TypeError):
            return None

    @staticmethod
    def ticket_key(ticket: str) -> str:
        return "ctf:terminal:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()

    async def issue(self, run_id: int, user_id: int, protocol: str | None = None,
                    target: str = "victim") -> str:
        if await self.is_closed(run_id):
            raise ValueError("El laboratorio se está cerrando")
        if target not in {"victim", "attacker"} or (target == "attacker" and protocol is None):
            raise ValueError("Destino no permitido")
        ticket = secrets.token_urlsafe(32)
        payload = {"run_id": run_id, "user_id": user_id}
        if protocol is not None:
            if protocol not in {"ssh", "rdp"}:
                raise ValueError("Protocolo no permitido")
            payload["protocol"] = protocol
        if target == "attacker":
            payload["target"] = target
        await self.redis.set(self.ticket_key(ticket), json.dumps(payload), ex=60)
        return ticket

    async def consume(self, ticket: str | None, run_id: int) -> dict | None:
        if not ticket or len(ticket) > 128 or await self.is_closed(run_id):
            return None
        encoded = await self.redis.getdel(self.ticket_key(ticket))
        if not encoded:
            return None
        payload = json.loads(encoded)
        return payload if payload.get("run_id") == run_id else None

    async def is_closed(self, run_id: int) -> bool:
        return bool(await self.redis.exists(f"ctf:terminal:closed:{run_id}"))

    async def close_run(self, run_id: int) -> None:
        # La marca distribuida impide nuevos túneles durante la limpieza SSH.
        await self.redis.set(f"ctf:terminal:closed:{run_id}", "1", ex=86400)
        for connection in list(self.connections.get(run_id, set())):
            try:
                await connection.close(code=1000)
            except Exception:
                pass

    async def forget_user(self, user_id: int) -> None:
        await self.redis.delete(f"ctf:terminal:user:{user_id}")

    async def shutdown(self) -> None:
        for run_id in list(self.connections):
            for connection in list(self.connections.get(run_id, set())):
                try:
                    await connection.close(code=1001)
                except Exception:
                    pass
