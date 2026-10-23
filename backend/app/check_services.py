"""Comprobación de producción de solo lectura, sin imprimir URLs ni secretos.

python -m app.check_services          comprueba PostgreSQL y Redis
python -m app.check_services --http   añade la respuesta HTTP de la API local
"""
from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request


async def check_postgres() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from .core import get_settings

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as connection:
            # Verifica autenticación y permiso de lectura sobre una tabla real.
            # No devuelve usuarios, no ejecuta DDL ni migra el esquema.
            await connection.execute(text("SELECT id FROM users LIMIT 0"))
    finally:
        await engine.dispose()


async def check_redis() -> None:
    from redis.asyncio import Redis
    from .core import get_settings

    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=4, socket_timeout=4)
    try:
        if not await client.ping():
            raise RuntimeError("Redis no respondió PONG")
    finally:
        await client.aclose()


def check_http() -> None:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=4) as response:
        body = json.load(response)
        if response.status != 200 or body.get("status") != "ok":
            raise RuntimeError("La API no respondió correctamente")


async def probe(name, action, timeout=6):
    try:
        await asyncio.wait_for(action(), timeout=timeout)
    except Exception:
        # Los mensajes de drivers pueden contener credenciales; no mostrarlos.
        return name, False
    return name, True


async def run_checks(include_http=False):
    checks = [("PostgreSQL (lectura de users)", check_postgres), ("Redis (PING)", check_redis)]
    if include_http:
        checks.append(("API HTTP", lambda: asyncio.to_thread(check_http)))
    return dict(await asyncio.gather(*(probe(name, action) for name, action in checks)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true")
    args = parser.parse_args(argv)
    results = asyncio.run(run_checks(args.http))
    for name, ok in results.items():
        print(f"{name}: {'OK' if ok else 'ERROR (revisar servicio, red y configuración privada)'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
