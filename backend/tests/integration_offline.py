"""Prueba PostgreSQL reversible: no persiste usuarios, puntos ni cambios al catálogo."""
import asyncio
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from fastapi import HTTPException
from app.db import make_session_factory
from app.models import Challenge, ChallengeRun, ChallengeFlag, User, StudentGroup, GroupMembership, ChallengeGroupAssignment
from app.api import runs
from app.api.challenges import list_challenges
from app.schemas import SubmissionRequest
from app.core import now_utc
from app.services.offline_catalog import configure
from app.services import offline_runtime
from app.domain.challenges.offline import CATALOG
from test_offline import solve


async def denied(action, expected):
    try: await action()
    except HTTPException as exc: assert exc.status_code == expected, exc.status_code
    else: raise AssertionError('La operación debió rechazarse')


async def main():
    base_factory = make_session_factory(); engine = base_factory.kw['bind']
    async with base_factory() as session:
        original_flags = await session.scalar(select(func.count(ChallengeFlag.id)))
    tag = uuid.uuid4().hex[:12]
    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(connection, expire_on_commit=False, join_transaction_mode='create_savepoint')
        try:
            async with factory() as session:
                await configure(session, '45HY')
                flag_count = await session.scalar(select(func.count(ChallengeFlag.id)))
                await configure(session, '45HY')
                assert await session.scalar(select(func.count(ChallengeFlag.id))) == flag_count, 'Conversión no idempotente'
                user = User(username='qa-offline-'+tag, password_hash='!disabled!', role='player')
                other = User(username='qa-other-'+tag, password_hash='!disabled!', role='player')
                group = await session.scalar(select(StudentGroup).where(StudentGroup.code=='45HY'))
                session.add_all([user,other]); await session.flush()
                session.add(GroupMembership(group_id=group.id,user_id=user.id)); await session.commit()
            request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=factory,
                redis=SimpleNamespace(incr=AsyncMock(return_value=1),expire=AsyncMock(),publish=AsyncMock()),
                sockets=SimpleNamespace(broadcast=AsyncMock()))))
            catalog = await list_challenges(request,difficulty=None,category=None,mitre=None,user=user)
            assert set(CATALOG).issubset({c.code for c in catalog})
            for code in [c.code for c in catalog if c.code in CATALOG and c.scenario != 'SSH-PASSWORD-LAB']:
                first = await runs.start_challenge(code,request,user)
                assert first.workspace_strategy=='offline_case' and first.launch_url is None
                assert (await runs.start_challenge(code,request,user)).id==first.id
                public = json.loads((await runs.get_offline_case(first.id,request,user)).body)
                assert 'files' not in public and 'sha256' not in public
                public, _ = offline_runtime.case_for(first, code)
                wrong = json.loads((await runs.answer_offline_case(first.id,runs.OfflineAnswer(value='incorrecta'),request,user)).body)
                assert not wrong['correct'] and wrong['flag'] is None
                await denied(lambda:runs.get_offline_case(first.id,request,other),404)
                await denied(lambda:runs.start_challenge(code,request,other),403)
                solved = json.loads((await runs.answer_offline_case(first.id,runs.OfflineAnswer(value=solve(code,public)),request,user)).body)
                assert solved['correct']
                result = await runs.submit_flag(code,SubmissionRequest(value=solved['flag']),request,user)
                assert result.correct and result.challenge_completed and result.awarded_points>0
                duplicate = await runs.submit_flag(code,SubmissionRequest(value=solved['flag']),request,user)
                assert duplicate.correct and duplicate.awarded_points==0
                await runs.close_run(first.id,request,user)
                await denied(lambda:runs.get_offline_case(first.id,request,user),409)
                second = await runs.start_challenge(code,request,user)
                rejected = await runs.submit_flag(code,SubmissionRequest(value=solved['flag']),request,user)
                assert not rejected.correct
                async with factory() as session:
                    run = await session.get(ChallengeRun,second.id); run.expires_at=now_utc()-timedelta(seconds=1); await session.commit()
                await denied(lambda:runs.get_offline_case(second.id,request,user),409)
                await denied(lambda:runs.answer_offline_case(second.id,runs.OfflineAnswer(value=solve(code,public)),request,user),409)
                await runs.close_run(second.id,request,user)
                print('PASS',code, 'descarga, solución pública, permisos, puntos únicos, cierre y caducidad',flush=True)
            first = await runs.start_challenge('CRY-01',request,user)
            async with factory() as session:
                challenge = await session.scalar(select(Challenge).where(Challenge.code=='CRY-01')); challenge.is_published=False; await session.commit()
            await denied(lambda:runs.get_offline_case(first.id,request,user),404)
            await runs.close_run(first.id,request,user)
        finally:
            await transaction.rollback()
    async with base_factory() as session:
        assert await session.scalar(select(User.id).where(User.username=='qa-offline-'+tag)) is None
        assert await session.scalar(select(func.count(ChallengeFlag.id)))==original_flags
    await engine.dispose()
    print('PASS: rollback confirmado; catálogo, usuarios y puntos reales conservados')


if __name__ == '__main__': asyncio.run(main())
