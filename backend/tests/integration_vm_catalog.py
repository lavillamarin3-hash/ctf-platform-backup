"""Prueba autorizada sobre Kali/LNX-VICT. Revierte SQL y elimina la cuenta temporal."""
import asyncio
import json
import re
import shlex
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
import paramiko
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from fastapi import HTTPException
from app.db import make_session_factory
from app.models import User, StudentGroup, GroupMembership
from app.guacamole import make_guacamole_admin
from app.services.vm_catalog import configure
from app.services import ssh_practice, offline_runtime
from app.api import runs, terminal
from app.schemas import SubmissionRequest
from test_offline import solve
from app.domain.challenges.offline import CATALOG


def remote(client,command,stdin=None):
    inp,out,err=client.exec_command(command,timeout=60)
    if stdin is not None:
        inp.write(stdin); inp.flush(); inp.channel.shutdown_write()
    output=out.read().decode()
    status=out.channel.recv_exit_status()
    if status!=0:
        errors=err.read().decode()
        raise AssertionError('Comando de prueba falló: '+str(status)+' '+errors[:1000])
    return output


def login_probe(client,user,password):
    code=("import paramiko\n"
          "c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())\n"
          "try:\n"
          f" c.connect('192.168.146.137',port=2222,username={user!r},password={password!r},timeout=8,allow_agent=False,look_for_keys=False)\n"
          " _,out,_=c.exec_command('cat flag.txt'); print(out.read().decode().strip())\n"
          "except paramiko.AuthenticationException: print('AUTH_REJECTED')\n"
          "finally: c.close()\n")
    return remote(client,'python3 -',code).strip()


async def main():
    factory=make_session_factory(); engine=factory.kw['bind']; tag=uuid.uuid4().hex[:8]
    guac=make_guacamole_admin(); connections=await guac.list_connections()
    kali=next(c for c in connections if c.hostname=='192.168.146.134' and c.protocol=='ssh')
    p=kali.parameters
    async with factory() as session:
        group=await session.scalar(select(StudentGroup).where(StudentGroup.code=='45HY'))
        real_user=await session.scalar(select(User).join(GroupMembership).where(GroupMembership.group_id==group.id,User.role=='player'))
        assert real_user
    permissions=await guac.get_user_permissions(real_user.username)
    client=paramiko.SSHClient(); client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('192.168.146.134',port=int(p.get('port') or 22),username=p['username'],password=p['password'],timeout=8,allow_agent=False,look_for_keys=False)
    ids=[]
    try:
        async with engine.connect() as connection:
            tx=await connection.begin()
            test_factory=async_sessionmaker(connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            try:
                async with test_factory() as session:
                    await configure(session)
                    user=User(username='qa-vm-'+tag,password_hash='!disabled!',role='player')
                    session.add(user); await session.flush()
                    session.add(GroupMembership(group_id=group.id,user_id=user.id)); await session.commit()
                request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=test_factory,
                    guacamole_admin=SimpleNamespace(list_connections=AsyncMock(return_value=connections),get_user_permissions=AsyncMock(return_value=permissions)),
                    redis=SimpleNamespace(incr=AsyncMock(return_value=1),expire=AsyncMock(),publish=AsyncMock()),
                    sockets=SimpleNamespace(broadcast=AsyncMock()),terminal_sessions=SimpleNamespace(close_run=AsyncMock()))))
                # Cada reto de análisis permite Kali, prepara los mismos bytes y conserva validación.
                for code in [c for c in CATALOG if c!=ssh_practice.CODE]+['DFIR-01']:
                    run=await runs.start_challenge(code,request,user)
                    assert run.target_vm_name=='LAB-KALI'
                    opts=await terminal.terminal_options(run.id,request,user); assert 'ssh' in opts['protocols']
                    target,_,_=await terminal.authorized_target(request.app,run.id,user.id,'ssh','victim'); assert target==kali.identifier
                    try: await terminal.authorized_target(request.app,run.id,user.id,'ssh','attacker')
                    except HTTPException as exc: assert exc.status_code==409
                    else: raise AssertionError('Se permitió otro destino')
                    endpoint=runs.get_dfir_case if code=='DFIR-01' else runs.get_offline_case
                    bundle=json.loads((await endpoint(run.id,request,user)).body)
                    # No escribir artefactos de prueba en la cuenta compartida: verificar comando y contenidos en memoria.
                    assert 'python3 -c' in bundle['kali_command']
                    assert 'files' not in bundle and 'sha256' not in bundle
                    if code!='DFIR-01':
                        bundle, _ = offline_runtime.case_for(run, code)
                        result=json.loads((await runs.answer_offline_case(run.id,runs.OfflineAnswer(value=solve(code,bundle)),request,user)).body)
                        assert result['correct']
                    await runs.close_run(run.id,request,user)
                    print('PASS terminal Kali y evidencias',code,flush=True)
                run=await runs.start_challenge(ssh_practice.CODE,request,user); ids.append(run.id)
                # Caso límite: la contraseña es la última de los 12 candidatos.
                identity=SimpleNamespace(id=run.id,user_id=user.id)
                await asyncio.to_thread(ssh_practice.provision,run.id,f'ctf{run.id}',ssh_practice.WORDS[-1],ssh_practice.flag_for(identity),run.expires_at.timestamp())
                info=json.loads((await runs.ssh_practice_info(run.id,request,user)).body)
                assert info['username']==f'ctf{run.id}'
                opts=await terminal.terminal_options(run.id,request,user); assert 'ssh' in opts['protocols']
                assert login_probe(client,info['username'],'definitely-wrong')=='AUTH_REJECTED'
                path=f'/tmp/ctf-qa-{run.id}.txt'
                dictionary="printf '%s\\n' "+' '.join(shlex.quote(w) for w in info['wordlist'])+' > '+shlex.quote(path)
                try:
                    remote(client,dictionary)
                    output=remote(client,f'hydra -I -l {info["username"]} -P {path} -t 1 -f -s 2222 192.168.146.137 ssh')
                    match=re.search(r'password:\s*(\S+)',output)
                    assert match,'Hydra no encontró la contraseña de la cuenta de práctica'
                    flag=login_probe(client,info['username'],match[1])
                    response=await runs.submit_flag(ssh_practice.CODE,SubmissionRequest(value=flag),request,user)
                    assert response.correct and response.awarded_points>0
                    again=await runs.submit_flag(ssh_practice.CODE,SubmissionRequest(value=flag),request,user)
                    assert again.awarded_points==0
                    await runs.close_run(run.id,request,user)
                    assert login_probe(client,info['username'],match[1])=='AUTH_REJECTED'
                    print('PASS Hydra real desde Kali, SSH, flag, puntos únicos y revocación al cerrar',flush=True)
                finally:
                    remote(client,'rm -f -- '+shlex.quote(path))
            finally:
                await tx.rollback()
    finally:
        client.close()
        for run_id in ids:
            await ssh_practice.cleanup(SimpleNamespace(id=run_id))
        async with factory() as session:
            assert await session.scalar(select(User.id).where(User.username=='qa-vm-'+tag)) is None
        await engine.dispose()
    print('PASS rollback: sin usuarios ni puntos de prueba persistidos')

if __name__=='__main__': asyncio.run(main())
