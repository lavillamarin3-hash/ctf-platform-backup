"""Regresiones del ciclo de laboratorio con dobles; no usa PostgreSQL, SSH ni Redis reales."""

import copy
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api import runs
from app.core import now_utc, verify_password
from app.domain.instances.states import InstanceState
from app.models import Challenge, ChallengeCompletion, ChallengeFlag, ChallengeInstance, ChallengeRun, ChallengeRunFlag, RemoteAccessAssignment, User, VMAsset, Laboratory
from app.schemas import SubmissionRequest
from app.services.dynamic_flags import DynamicFlagRuntime
from app.services.lab_lock import (
    LabReservationBusy, LabReservationError, LabReservationUnavailable,
    acquire, release, reservation_key, reserve_for_cleanup,
)


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.publish = AsyncMock()
        self.fail_release = False
        self.fail_set = False

    async def set(self, key, token, *, nx, ex):
        if self.fail_set:
            raise RuntimeError("Error interno del servidor Redis")
        if key in self.values:
            return False
        self.values[key] = token
        return True

    async def eval(self, script, key_count, key, token, *extra):
        current = self.values.get(key)
        if "'expire'" in script:
            if current is None or current == token:
                self.values[key] = token
                return 1
            return 0
        if self.fail_release:
            raise RuntimeError("Redis no disponible al liberar")
        if current is None:
            return 1
        if current == token:
            self.values.pop(key, None)
            return 1
        return 0


class MemoryInjector:
    def __init__(self):
        self.preflight = AsyncMock()
        self.probe_authentication = AsyncMock()
        self.files = {}
        self.injected = []
        self.cleared = []
        self.fail_inject = False
        self.fail_clear = False

    async def inject(self, ip, path, value, os):
        self.files[(ip, path)] = value
        self.injected.append((ip, path, value))
        if self.fail_inject:
            raise RuntimeError("Falló el transporte con un dato interno sensible")

    async def clear(self, ip, path, os):
        self.cleared.append((ip, path))
        if self.fail_clear:
            raise RuntimeError("Falló la limpieza remota")
        self.files.pop((ip, path), None)


class MemoryGuacamole:
    def __init__(self):
        self.permissions = {"systemPermissions": ["AUDIT"], "connectionPermissions": {"other": ["READ"]}}
        self.patches = []
        self.revoke = AsyncMock()

    async def get_user_permissions(self, username):
        return copy.deepcopy(self.permissions)

    async def patch_user_permissions(self, username, *, system_permissions, connection_permissions):
        self.permissions = {"systemPermissions": system_permissions, "connectionPermissions": connection_permissions}
        self.patches.append(copy.deepcopy(self.permissions))

    async def direct_connection_url(self, identifier):
        return "https://terminal.test/#/client/opaque-id"


class MemorySession:
    def __init__(self, scalar_results=(), *, objects=None, run_id=101, scalar_lists=()):
        self.scalar_results = list(scalar_results)
        self.scalar_lists = list(scalar_lists)
        self.objects = objects or {}
        self.added = []
        self.run_id = run_id
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalar(self, statement):
        if not self.scalar_results:
            raise AssertionError("Consulta inesperada en el doble de sesión")
        return self.scalar_results.pop(0)

    async def scalars(self, statement):
        values = self.scalar_lists.pop(0)
        return SimpleNamespace(all=lambda: list(values))

    async def get(self, model, identifier):
        return self.objects.get((model, identifier))

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, ChallengeRun) and value.id is None:
                value.id = self.run_id
                value.started_at = now_utc()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class RunLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.flag = ChallengeFlag(id=11, mode="dynamic", flag_order=1, is_active=True,
                                  template="FLAG{lab-01_{{USER}}_{{RUN_ID}}_{{RAND}}}", label="Evidencia")
        self.challenge = Challenge(id=1, code="LAB-01", is_published=True, points=100, flags=[self.flag])
        self.user = SimpleNamespace(id=8, username="student-test", role="player")
        self.vm = SimpleNamespace(id=4, name="victim-test", ip_address="192.0.2.14", os="Linux",
                                  laboratory_id=2, guacamole_connection_id="connection-test")
        self.lab = SimpleNamespace(id=2, code="LAB-TEST")
        self.connection = SimpleNamespace(identifier="connection-test", protocol="ssh")
        self.settings = SimpleNamespace(flag_injector_lock_ttl_seconds=5400, flag_injector_flag_path="/opt/ctf/flag.txt",
                                        flag_injector_enabled=True)
        self.redis = MemoryRedis()
        self.injector = MemoryInjector()
        self.guacamole = MemoryGuacamole()
        self.terminal = SimpleNamespace(close_run=AsyncMock())
        self.objects = {(User, self.user.id): self.user, (VMAsset, self.vm.id): self.vm,
                        (Laboratory, self.lab.id): self.lab}
        self.patches = [
            patch.object(runs, "get_settings", return_value=self.settings),
            patch("app.services.dynamic_flags.get_settings", return_value=self.settings),
            patch.object(runs, "check_rate_limit", new=AsyncMock()),
            patch.object(runs, "write_audit", new=AsyncMock()),
            patch.object(runs, "_assigned", new=AsyncMock(return_value=True)),
            patch.object(runs, "_find_challenge_vm", new=AsyncMock(return_value=(self.lab, self.vm))),
            patch.object(runs, "_resolve_guacamole_connection", new=AsyncMock(return_value=self.connection)),
            patch.object(runs, "_connection_protocol", new=AsyncMock(return_value="ssh")),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def request(self, session):
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            session_factory=lambda: session, redis=self.redis, flag_injector=self.injector,
            guacamole=self.guacamole, guacamole_admin=self.guacamole,
            terminal_sessions=self.terminal, sockets=SimpleNamespace(broadcast=AsyncMock()),
        )))

    def active_run(self, identifier=101):
        return SimpleNamespace(id=identifier, user_id=self.user.id, challenge_id=self.challenge.id,
            status="active", started_at=now_utc(), expires_at=now_utc() + timedelta(hours=1),
            workspace_strategy="shared_lab_vm", closed_at=None,
            assignment=SimpleNamespace(status="active", external_reference=f"run:{identifier}", launch_url="https://terminal.test"))

    def instance(self, run_id=101, *, preexisting=False):
        return ChallengeInstance(id=21, challenge_id=1, vm_asset_id=self.vm.id, run_id=run_id,
            user_id=self.user.id, state=InstanceState.IN_USE.value, guacamole_connection_id=self.connection.identifier,
            guacamole_access_granted=True, guacamole_access_preexisting=preexisting)

    async def test_rejected_reservation_never_clears_other_run_flag_or_grants_read(self):
        path = (self.vm.ip_address, "/opt/ctf/flag.txt")
        self.injector.files[path] = "FLAG{another-run}"
        self.redis.values[reservation_key(self.vm.ip_address)] = "77"
        session = MemorySession([self.challenge, None], objects=self.objects)
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("reservada por otra ejecución", raised.exception.detail)
        self.assertNotIn(self.vm.ip_address, raised.exception.detail)
        self.assertEqual(self.injector.files[path], "FLAG{another-run}")
        self.assertEqual(self.injector.cleared, [])
        self.assertEqual(self.guacamole.patches, [])
        self.guacamole.revoke.assert_not_awaited()
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], "77")

    async def test_occupied_pool_after_ttl_does_not_touch_old_evidence(self):
        session = MemorySession([self.challenge, None, self.instance(77)], objects=self.objects)
        path = (self.vm.ip_address, "/opt/ctf/flag.txt")
        self.injector.files[path] = "FLAG{old-run}"
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("sigue marcada en uso", raised.exception.detail)
        self.assertNotIn(self.vm.ip_address, raised.exception.detail)
        self.assertEqual(self.injector.files[path], "FLAG{old-run}")
        self.assertEqual(self.injector.cleared, [])
        self.assertEqual(self.guacamole.patches, [])
        self.guacamole.revoke.assert_not_awaited()
        self.assertNotIn(reservation_key(self.vm.ip_address), self.redis.values)

    async def test_redis_unavailable_reports_retry_without_claiming_vm_busy(self):
        self.redis.fail_set = True
        session = MemorySession([self.challenge, None], objects=self.objects)
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("Redis esté disponible", raised.exception.detail)
        self.assertNotIn("Error interno", raised.exception.detail)
        self.assertEqual(self.injector.injected, [])
        self.assertEqual(self.guacamole.patches, [])

    async def test_partial_injection_failure_cleans_only_own_resources(self):
        self.injector.fail_inject = True
        session = MemorySession([self.challenge, None, None], objects=self.objects)
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("acceso SSH del inyector", raised.exception.detail)
        self.assertNotIn("sensible", raised.exception.detail)
        self.assertEqual(self.injector.files, {})
        self.assertEqual(self.redis.values, {})
        self.assertEqual(self.guacamole.permissions["connectionPermissions"], {"other": ["READ"]})
        self.assertEqual(self.guacamole.permissions["systemPermissions"], ["AUDIT"])

    async def test_failed_start_does_not_claim_release_when_redis_cannot_confirm_it(self):
        self.injector.fail_inject = True
        self.redis.fail_release = True
        session = MemorySession([self.challenge, None, None], objects=self.objects)
        with self.assertLogs(runs.logger, level="WARNING") as logs:
            with self.assertRaises(HTTPException) as raised:
                await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn(reservation_key(self.vm.ip_address), self.redis.values)
        self.assertEqual(self.injector.files, {})
        self.assertEqual(session.commits, 0)
        self.assertTrue(any("liberación Redis no confirmada" in line for line in logs.output))
        self.assertNotIn("FLAG{", " ".join(logs.output))

    async def test_guacamole_permission_failure_reports_stage_and_releases_lease(self):
        self.guacamole.get_user_permissions = AsyncMock(side_effect=RuntimeError("dato sensible remoto"))
        session = MemorySession([self.challenge, None, None], objects=self.objects)
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("permisos de Guacamole", raised.exception.detail)
        self.assertNotIn("sensible", raised.exception.detail)
        self.assertEqual(self.redis.values, {})
        self.assertEqual(self.injector.injected, [])

    async def test_existing_active_run_is_reused_without_regeneration(self):
        existing = self.active_run()
        session = MemorySession([self.challenge, existing, self.instance()], objects=self.objects)
        result = await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(result.id, existing.id)
        self.assertEqual(self.injector.injected, [])
        self.assertEqual(session.added, [])
        self.assertEqual(self.guacamole.patches, [])

    async def test_existing_run_uses_original_instance_target_after_challenge_edit(self):
        existing, instance = self.active_run(), self.instance()
        instance.guacamole_connection_id = "original-connection"
        session = MemorySession([self.challenge, existing, instance], objects=self.objects)
        request = self.request(session)
        protocol = AsyncMock(return_value="ssh")
        with patch.object(runs, "_find_challenge_vm", new=AsyncMock(side_effect=AssertionError("No resolver destino nuevo"))), \
             patch.object(runs, "_connection_protocol", new=protocol):
            result = await runs.start_challenge("LAB-01", request, self.user)
        self.assertEqual(result.target_vm_ip, self.vm.ip_address)
        self.assertEqual(result.target_vm_name, self.vm.name)
        protocol.assert_awaited_once_with(request, "original-connection")
        self.assertEqual(self.injector.injected, [])

    async def test_existing_legacy_run_without_instance_uses_challenge_fallback(self):
        existing = self.active_run()
        session = MemorySession([self.challenge, existing, None], objects=self.objects)
        result = await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(result.id, existing.id)
        self.assertEqual(result.target_vm_ip, self.vm.ip_address)
        self.assertEqual(self.injector.injected, [])

    async def test_dynamic_lab_rejects_non_ssh_connection_before_reservation(self):
        session = MemorySession([self.challenge, None], objects=self.objects)
        connection = SimpleNamespace(identifier="rdp-test", protocol="rdp")
        with patch.object(runs, "_resolve_guacamole_connection", new=AsyncMock(return_value=connection)):
            with self.assertRaises(HTTPException) as raised:
                await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(session.added, [])
        self.assertEqual(self.redis.values, {})

    async def test_unreachable_victim_ssh_fails_before_run_or_redis_reservation(self):
        self.injector.preflight.side_effect = RuntimeError("detalle técnico privado")
        session = MemorySession([self.challenge, None], objects=self.objects)
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("no acepta SSH desde la API", raised.exception.detail)
        self.assertNotIn("privado", raised.exception.detail)
        self.assertEqual(session.added, [])
        self.assertEqual(self.redis.values, {})
        self.assertEqual(self.injector.injected, [])

    async def test_injector_authentication_failure_fails_before_run_or_reservation(self):
        self.injector.probe_authentication.side_effect = RuntimeError("dato privado de autenticación")
        session = MemorySession([self.challenge, None], objects=self.objects)
        with self.assertRaises(HTTPException) as raised:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("inyector no puede autenticarse", raised.exception.detail)
        self.assertNotIn("dato privado", raised.exception.detail)
        self.assertEqual(session.added, [])
        self.assertEqual(self.redis.values, {})
        self.assertEqual(self.injector.injected, [])

    async def test_close_cleans_physical_flag_redis_terminal_and_temporary_read(self):
        run, instance = self.active_run(), self.instance()
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        self.redis.values[reservation_key(self.vm.ip_address)] = str(run.id)
        self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")] = "FLAG{test}"
        self.guacamole.permissions["connectionPermissions"][self.connection.identifier] = ["READ", "UPDATE"]
        result = await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(result.status, "closed")
        self.assertEqual(instance.state, InstanceState.AVAILABLE.value)
        self.assertIsNone(instance.run_id)
        self.assertFalse(instance.guacamole_access_granted)
        self.assertEqual(self.injector.files, {})
        self.assertEqual(self.redis.values, {})
        self.assertEqual(self.guacamole.permissions["connectionPermissions"], {"other": ["READ"], self.connection.identifier: ["UPDATE"]})
        self.terminal.close_run.assert_awaited_once_with(run.id)

    async def test_opt_in_code_path_is_used_for_start_and_cleanup(self):
        self.settings.flag_injector_flag_path = "/opt/ctf/{{CODE}}/flag.txt"
        path = (self.vm.ip_address, "/opt/ctf/LAB-01/flag.txt")
        start_session = MemorySession([self.challenge, None, None], objects=self.objects)
        started = await runs.start_challenge("LAB-01", self.request(start_session), self.user)
        self.assertEqual(started.status, "active")
        self.assertIn(path, self.injector.files)
        self.assertNotIn((self.vm.ip_address, "/opt/ctf/flag.txt"), self.injector.files)

        close_session = MemorySession([self.active_run(started.id), self.challenge, self.instance(started.id)], objects=self.objects)
        await runs.close_run(started.id, self.request(close_session), self.user)
        self.assertNotIn(path, self.injector.files)
        self.assertIn(path, self.injector.cleared)

    async def test_esc_evidence_path_and_cleanup_do_not_touch_lab01(self):
        runtime = DynamicFlagRuntime(self.injector)
        session = MemorySession()
        esc_flag = ChallengeFlag(id=12, mode="dynamic", flag_order=1, is_active=True,
                                 template="FLAG{esc-01_{{USER}}_{{RUN_ID}}_{{RAND}}}")
        esc = Challenge(id=2, code="ESC-01-RECON", flags=[esc_flag])
        lab_path = (self.vm.ip_address, "/opt/ctf/flag.txt")
        esc_path = (self.vm.ip_address, "/opt/ctf/ESC-01-RECON/flag.txt")

        await runtime.prepare(session, self.challenge, SimpleNamespace(id=101), self.user.username, self.vm)
        await runtime.prepare(session, esc, SimpleNamespace(id=102), self.user.username, self.vm)
        self.assertEqual(set(self.injector.files), {lab_path, esc_path})

        await runtime.cleanup(session, 102, esc, self.vm)
        self.assertEqual(set(self.injector.files), {lab_path})
        self.assertEqual(self.injector.cleared[-1], esc_path)
        await runtime.cleanup(session, 101, self.challenge, self.vm)
        self.assertEqual(self.injector.files, {})

    async def test_esc_start_never_grants_victim_read_or_exposes_its_launch_url(self):
        self.challenge.code = "ESC-01-RECON"
        self.challenge.id = 2
        self.settings.guacamole_base_url = "https://guacamole.test"
        session = MemorySession([self.challenge, None, None], objects=self.objects)
        with patch.object(self.guacamole, "direct_connection_url", new=AsyncMock(
            side_effect=AssertionError("No debe generar enlace directo a la víctima")
        )):
            result = await runs.start_challenge(self.challenge.code, self.request(session), self.user)
        assignment = next(item for item in session.added if isinstance(item, RemoteAccessAssignment))
        instance = next(item for item in session.added if isinstance(item, ChallengeInstance))
        self.assertIsNone(result.launch_url)
        self.assertEqual(assignment.launch_url, "https://guacamole.test/#/home")
        self.assertNotIn("#/client/", assignment.launch_url)
        self.assertIsNone(result.target_protocol)
        self.assertEqual(self.guacamole.patches, [])
        self.assertFalse(instance.guacamole_access_granted)
        self.assertFalse(instance.guacamole_access_preexisting)
        self.assertEqual(runs._player_launch_url(self.challenge, self.active_run().assignment), None)
        self.assertEqual(len(self.injector.injected), 1)

    async def test_esc_rejects_two_dynamic_flags_before_injection(self):
        runtime = DynamicFlagRuntime(self.injector)
        other = ChallengeFlag(id=12, mode="dynamic", flag_order=2, is_active=True,
                              template="FLAG{esc-02_{{USER}}_{{RUN_ID}}_{{RAND}}}")
        esc = Challenge(id=2, code="ESC-01-RECON", flags=[self.flag, other])
        with self.assertRaisesRegex(ValueError, "una sola flag"):
            await runtime.prepare(MemorySession(), esc, SimpleNamespace(id=102), self.user.username, self.vm)
        self.assertEqual(self.injector.injected, [])

    async def test_opt_in_code_path_rollback_cleans_only_that_path(self):
        self.settings.flag_injector_flag_path = "/opt/ctf/{{CODE}}/flag.txt"
        self.injector.fail_inject = True
        session = MemorySession([self.challenge, None, None], objects=self.objects)
        with self.assertRaises(HTTPException):
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(self.injector.files, {})
        self.assertTrue(self.injector.cleared)
        self.assertTrue(all(path == "/opt/ctf/LAB-01/flag.txt" for _, path in self.injector.cleared))

    def test_code_path_rejects_unsafe_code_or_template(self):
        runtime = DynamicFlagRuntime(self.injector)
        runtime.settings = self.settings
        self.settings.flag_injector_flag_path = "/opt/ctf/{{CODE}}/flag.txt"
        with self.assertRaises(ValueError):
            runtime.path_for(self.flag, "../OTHER")
        with self.assertRaises(ValueError):
            runtime.path_for(self.flag, "lab-01")
        self.settings.flag_injector_flag_path = "/opt/ctf/{{CODE}}/../flag.txt"
        with self.assertRaises(ValueError):
            runtime.path_for(self.flag, "LAB-01")
        self.settings.flag_injector_flag_path = "/opt/ctf/{{UNKNOWN}}/flag.txt"
        with self.assertRaises(ValueError):
            runtime.path_for(self.flag, "LAB-01")

    async def test_invalid_code_path_fails_before_lock_or_injection(self):
        self.settings.flag_injector_flag_path = "/opt/ctf/{{CODE}}/../flag.txt"
        session = MemorySession([self.challenge, None], objects=self.objects)
        with self.assertRaises(HTTPException) as error:
            await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("configuración de la flag", error.exception.detail)
        self.assertEqual(self.redis.values, {})
        self.assertEqual(self.injector.injected, [])
        self.assertEqual(self.injector.cleared, [])

    async def test_close_preserves_preexisting_read(self):
        run, instance = self.active_run(), self.instance(preexisting=True)
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        self.guacamole.permissions["connectionPermissions"][self.connection.identifier] = ["READ"]
        await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(self.guacamole.permissions["connectionPermissions"][self.connection.identifier], ["READ"])
        self.assertEqual(self.guacamole.patches, [])

    async def test_owner_can_close_after_group_assignment_is_revoked(self):
        run, instance = self.active_run(), self.instance()
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        with patch.object(runs, "_assigned", new=AsyncMock(return_value=False)):
            result = await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(result.status, "closed")
        self.assertIsNone(instance.run_id)

    async def test_close_uses_original_reserved_vm_even_if_challenge_changed(self):
        run, instance = self.active_run(), self.instance()
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        with patch.object(runs, "_find_challenge_vm", new=AsyncMock(side_effect=AssertionError("No resolver reto modificado"))):
            await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(self.injector.cleared, [(self.vm.ip_address, "/opt/ctf/flag.txt")])

    async def test_close_refuses_to_clear_when_redis_belongs_to_new_run(self):
        run, instance = self.active_run(), self.instance()
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        self.redis.values[reservation_key(self.vm.ip_address)] = "777"
        with self.assertRaises(HTTPException):
            await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(run.status, "active")
        self.assertEqual(instance.run_id, run.id)
        self.assertEqual(self.injector.cleared, [])
        self.terminal.close_run.assert_not_awaited()

    async def test_failed_physical_cleanup_keeps_pool_and_lock_for_retry(self):
        run, instance = self.active_run(), self.instance()
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        self.injector.fail_clear = True
        with self.assertRaises(HTTPException) as raised:
            await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(run.status, "active")
        self.assertEqual(instance.run_id, run.id)
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], str(run.id))
        self.assertEqual(session.commits, 0)

    async def test_redis_release_error_never_reports_success_or_returns_pool(self):
        run, instance = self.active_run(), self.instance()
        session = MemorySession([run, self.challenge, instance], objects=self.objects)
        self.redis.values[reservation_key(self.vm.ip_address)] = str(run.id)
        self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")] = "FLAG{test}"
        self.redis.fail_release = True
        with self.assertRaises(HTTPException) as raised:
            await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("liberar la reserva", raised.exception.detail)
        self.assertEqual(self.injector.files, {})
        self.assertEqual(run.status, "active")
        self.assertEqual(instance.run_id, run.id)
        self.assertEqual(instance.state, InstanceState.IN_USE.value)
        self.assertEqual(session.commits, 0)
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], str(run.id))
        # El mismo cierre puede reintentarse aunque la evidencia ya no exista.
        self.redis.fail_release = False
        retry_session = MemorySession([run, self.challenge, instance], objects=self.objects)
        result = await runs.close_run(run.id, self.request(retry_session), self.user)
        self.assertEqual(result.status, "closed")
        self.assertEqual(instance.state, InstanceState.AVAILABLE.value)
        self.assertEqual(self.redis.values, {})

    async def test_repeated_close_is_idempotent_and_does_not_touch_successor(self):
        run = self.active_run()
        run.status, run.assignment.status = "closed", "revoked"
        session = MemorySession([run, self.challenge], objects=self.objects)
        self.redis.values[reservation_key(self.vm.ip_address)] = "777"
        result = await runs.close_run(run.id, self.request(session), self.user)
        self.assertEqual(result.status, "closed")
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], "777")
        self.assertEqual(self.injector.cleared, [])
        self.terminal.close_run.assert_not_awaited()

    async def test_expired_start_cleans_previous_run_before_reusing_instance(self):
        expired = self.active_run(100)
        expired.expires_at = now_utc() - timedelta(seconds=1)
        instance = self.instance(100)
        session = MemorySession([self.challenge, expired, instance, instance], objects=self.objects, run_id=101)
        self.redis.values[reservation_key(self.vm.ip_address)] = "100"
        self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")] = "FLAG{previous-run}"
        result = await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(expired.status, "expired")
        self.assertEqual(expired.assignment.status, "expired")
        self.assertEqual(result.id, 101)
        self.assertEqual(instance.run_id, 101)
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], "101")
        self.assertNotEqual(self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")], "FLAG{previous-run}")
        self.terminal.close_run.assert_awaited_once_with(100)

    async def test_expiration_worker_cleans_without_student_returning(self):
        expired, instance = self.active_run(), self.instance()
        expired.expires_at = now_utc() - timedelta(seconds=1)
        discovery = MemorySession(scalar_lists=[[expired.id]])
        cleanup = MemorySession([expired, self.challenge, instance], objects=self.objects)
        request = self.request(discovery)
        sessions = iter([discovery, cleanup])
        request.app.state.session_factory = lambda: next(sessions)
        self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")] = "FLAG{expired}"
        result = await runs.expire_stale_runs(request)
        self.assertEqual(result, {"cleaned": 1, "pending": 0})
        self.assertEqual(expired.status, "expired")
        self.assertIsNone(instance.run_id)
        self.assertEqual(self.injector.files, {})
        self.assertEqual(self.redis.values, {})

    async def test_expiration_worker_retains_failed_cleanup_for_retry(self):
        expired, instance = self.active_run(), self.instance()
        expired.expires_at = now_utc() - timedelta(seconds=1)
        discovery = MemorySession(scalar_lists=[[expired.id]])
        cleanup = MemorySession([expired, self.challenge, instance], objects=self.objects)
        request = self.request(discovery)
        sessions = iter([discovery, cleanup])
        request.app.state.session_factory = lambda: next(sessions)
        self.injector.fail_clear = True
        result = await runs.expire_stale_runs(request)
        self.assertEqual(result, {"cleaned": 0, "pending": 1})
        self.assertEqual(expired.status, "active")
        self.assertEqual(instance.run_id, expired.id)
        self.assertEqual(cleanup.rollbacks, 1)
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], str(expired.id))

    async def test_start_close_start_reuses_instance_and_generates_new_flag(self):
        session_first = MemorySession([self.challenge, None, None], objects=self.objects, run_id=101)
        await runs.start_challenge("LAB-01", self.request(session_first), self.user)
        first_value = self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")]
        instance = next(value for value in session_first.added if isinstance(value, ChallengeInstance))
        first_hash = next(value.flag_hash for value in session_first.added if isinstance(value, ChallengeRunFlag))
        self.assertTrue(verify_password(first_value, first_hash))
        run = self.active_run(101)
        close_session = MemorySession([run, self.challenge, instance], objects=self.objects)
        await runs.close_run(run.id, self.request(close_session), self.user)
        session_second = MemorySession([self.challenge, None, instance], objects=self.objects, run_id=102)
        await runs.start_challenge("LAB-01", self.request(session_second), self.user)
        second_value = self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")]
        second_hash = next(value.flag_hash for value in session_second.added if isinstance(value, ChallengeRunFlag))
        self.assertNotEqual(first_value, second_value)
        self.assertTrue(verify_password(second_value, second_hash))
        self.assertFalse(verify_password(first_value, second_hash))
        self.assertEqual(instance.run_id, 102)
        self.assertFalse(any(isinstance(value, ChallengeInstance) for value in session_second.added))

    async def test_closed_run_can_reopen_for_a_different_assigned_student(self):
        first_session = MemorySession([self.challenge, None, None], objects=self.objects, run_id=101)
        await runs.start_challenge("LAB-01", self.request(first_session), self.user)
        instance = next(value for value in first_session.added if isinstance(value, ChallengeInstance))
        first_value = self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")]
        close_session = MemorySession([self.active_run(101), self.challenge, instance], objects=self.objects)
        await runs.close_run(101, self.request(close_session), self.user)

        next_user = SimpleNamespace(id=9, username="second-student", role="player")
        self.objects[(User, next_user.id)] = next_user
        second_session = MemorySession([self.challenge, None, instance], objects=self.objects, run_id=102)
        reopened = await runs.start_challenge("LAB-01", self.request(second_session), next_user)
        self.assertEqual(reopened.id, 102)
        self.assertEqual(instance.user_id, next_user.id)
        self.assertEqual(self.redis.values[reservation_key(self.vm.ip_address)], "102")
        self.assertNotEqual(self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")], first_value)

    async def test_correct_and_incorrect_submissions_validate_backend_hash(self):
        run = self.active_run()
        preparation = MemorySession(objects=self.objects)
        await DynamicFlagRuntime(self.injector).prepare(preparation, self.challenge, run, self.user.username, self.vm)
        run_flag = next(value for value in preparation.added if isinstance(value, ChallengeRunFlag))
        value = self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")]
        incorrect_session = MemorySession([self.challenge, run, run_flag], objects=self.objects)
        incorrect = await runs.submit_flag("LAB-01", SubmissionRequest(value="FLAG{wrong}"), self.request(incorrect_session), self.user)
        self.assertFalse(incorrect.correct)
        correct_session = MemorySession([self.challenge, run, run_flag, None], objects=self.objects, scalar_lists=[[]])
        with patch.object(runs, "ranking_rows", new=AsyncMock(return_value=[])):
            correct = await runs.submit_flag("LAB-01", SubmissionRequest(value=value), self.request(correct_session), self.user)
        self.assertTrue(correct.correct)
        self.assertTrue(correct.challenge_completed)
        self.assertEqual(correct.awarded_points, 100)

    async def test_explicit_static_lab01_uses_catalog_hash_without_injection(self):
        from app.core import hash_password
        self.flag.mode = "static"
        self.flag.template = None
        self.flag.validator = "exact_hash_explicit"
        self.flag.flag_hash = hash_password("FLAG{static_lab01_test}")
        start_session = MemorySession([self.challenge, None], objects=self.objects)
        started = await runs.start_challenge("LAB-01", self.request(start_session), self.user)
        self.assertEqual(started.status, "active")
        self.assertEqual(self.injector.injected, [])
        self.assertEqual(self.injector.cleared, [])
        self.assertEqual(self.redis.values, {})

        run = self.active_run()
        wrong_session = MemorySession([self.challenge, run], objects=self.objects)
        wrong = await runs.submit_flag("LAB-01", SubmissionRequest(value="FLAG{wrong}"), self.request(wrong_session), self.user)
        self.assertFalse(wrong.correct)
        correct_session = MemorySession([self.challenge, run, None], objects=self.objects, scalar_lists=[[]])
        with patch.object(runs, "ranking_rows", new=AsyncMock(return_value=[])):
            correct = await runs.submit_flag("LAB-01", SubmissionRequest(value="FLAG{static_lab01_test}"), self.request(correct_session), self.user)
        self.assertTrue(correct.correct)
        self.assertTrue(correct.challenge_completed)
        self.assertEqual(correct.awarded_points, 100)

    async def test_existing_completion_reports_complete_without_duplicate_points(self):
        run = self.active_run()
        preparation = MemorySession(objects=self.objects)
        await DynamicFlagRuntime(self.injector).prepare(preparation, self.challenge, run, self.user.username, self.vm)
        run_flag = next(value for value in preparation.added if isinstance(value, ChallengeRunFlag))
        value = self.injector.files[(self.vm.ip_address, "/opt/ctf/flag.txt")]
        existing = ChallengeCompletion(user_id=self.user.id, challenge_id=self.challenge.id, awarded_points=100)
        session = MemorySession([self.challenge, run, run_flag, existing], objects=self.objects, scalar_lists=[[self.flag.id]])
        request = self.request(session)
        result = await runs.submit_flag("LAB-01", SubmissionRequest(value=value), request, self.user)
        self.assertTrue(result.correct)
        self.assertTrue(result.challenge_completed)
        self.assertEqual(result.awarded_points, 0)
        self.assertNotIn("restantes", result.message)
        self.assertFalse(any(isinstance(value, ChallengeCompletion) for value in session.added))
        request.app.state.sockets.broadcast.assert_not_awaited()

    async def test_unassigned_player_cannot_start(self):
        session = MemorySession([self.challenge], objects=self.objects)
        with patch.object(runs, "_assigned", new=AsyncMock(return_value=False)):
            with self.assertRaises(HTTPException) as raised:
                await runs.start_challenge("LAB-01", self.request(session), self.user)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(session.added, [])
        self.assertEqual(self.injector.injected, [])


class LabLeaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_release_does_not_delete_other_owners_lock(self):
        redis = MemoryRedis()
        await acquire(redis, "192.0.2.1", 1, 60)
        with self.assertRaises(LabReservationBusy):
            await acquire(redis, "192.0.2.1", 2, 60)
        self.assertFalse(await release(redis, "192.0.2.1", "2"))
        self.assertEqual(redis.values[reservation_key("192.0.2.1")], "1")

    async def test_release_is_confirmed_and_idempotent_when_reservation_absent(self):
        redis = MemoryRedis()
        self.assertTrue(await release(redis, "192.0.2.1", "1"))
        await acquire(redis, "192.0.2.1", 1, 60)
        self.assertTrue(await release(redis, "192.0.2.1", "1"))
        self.assertTrue(await release(redis, "192.0.2.1", "1"))
        self.assertEqual(redis.values, {})

    async def test_cleanup_recovers_expired_own_lease_but_rejects_successor(self):
        redis = MemoryRedis()
        self.assertEqual(await reserve_for_cleanup(redis, "192.0.2.1", 1, 60), "1")
        self.assertEqual(await reserve_for_cleanup(redis, "192.0.2.1", 1, 60), "1")
        redis.values[reservation_key("192.0.2.1")] = "2"
        with self.assertRaises(LabReservationBusy):
            await reserve_for_cleanup(redis, "192.0.2.1", 1, 60)
        self.assertEqual(redis.values[reservation_key("192.0.2.1")], "2")

    async def test_acquire_distinguishes_unavailable_redis_from_busy_lease(self):
        redis = MemoryRedis()
        redis.fail_set = True
        with self.assertRaises(LabReservationUnavailable):
            await acquire(redis, "192.0.2.1", 1, 60)
        self.assertEqual(redis.values, {})


if __name__ == "__main__":
    unittest.main()
