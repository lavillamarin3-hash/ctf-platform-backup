"""Vista previa por defecto; --apply actualiza textos estándar, sin cambiar resultados."""
import argparse
import asyncio
import json
from sqlalchemy import select
from app.db import make_session_factory
from app.models import Challenge
from app.services.bootstrap import write_audit
from app.services.kali_instructions import update_text


async def main(apply):
    factory = make_session_factory()
    try:
        async with factory() as session:
            changed = []
            challenges = (await session.scalars(select(Challenge).order_by(Challenge.id).with_for_update())).all()
            for challenge in challenges:
                if not {'OFFLINE-CASE', 'DFIR-CASE'}.intersection(challenge.asset_references or []):
                    continue
                before = {key: getattr(challenge, key) for key in ('instructions', 'description')}
                after = {key: update_text(value) for key, value in before.items()}
                if before == after:
                    continue
                changed.append(challenge.code)
                if apply:
                    for key, value in after.items():
                        setattr(challenge, key, value)
                    await write_audit(session, None, 'challenge.kali.instructions', 'challenge', str(challenge.id),
                                      {'code': challenge.code, 'before': before, 'after': after})
            if apply:
                await session.commit()
            else:
                await session.rollback()
            print(json.dumps({'applied': apply, 'changed': changed}, ensure_ascii=False))
    finally:
        await factory.kw['bind'].dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args().apply))
