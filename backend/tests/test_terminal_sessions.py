"""Tickets efímeros, cifrado y revocación de terminal con Redis en memoria."""

import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from app.services.terminal_sessions import TerminalSessions


class ExpiringRedis:
    def __init__(self):
        self.now = 0
        self.values = {}
        self.expires = {}
        self.getdel_calls = 0

    async def set(self, key, value, *, ex):
        self.values[key] = value
        self.expires[key] = self.now + ex
        return True

    async def get(self, key):
        if self.expires.get(key, 0) <= self.now:
            self.values.pop(key, None)
            self.expires.pop(key, None)
        return self.values.get(key)

    async def getdel(self, key):
        self.getdel_calls += 1
        value = await self.get(key)
        await self.delete(key)
        return value

    async def exists(self, key):
        return int(await self.get(key) is not None)

    async def delete(self, key):
        existed = key in self.values
        self.values.pop(key, None)
        self.expires.pop(key, None)
        return int(existed)


class TerminalSessionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(field_hmac_secret="unit-test-private-key", access_token_minutes=20)
        self.settings_patch = patch("app.services.terminal_sessions.get_settings", return_value=self.settings)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.redis = ExpiringRedis()
        self.sessions = TerminalSessions(self.redis)
        self.delegated = {"token": "personal-token-only-in-test", "username": "student-test", "data_source": "postgresql"}

    async def test_personal_token_is_encrypted_and_shared_between_workers(self):
        await self.sessions.remember_user(8, self.delegated)
        encoded = self.redis.values["ctf:terminal:user:8"]
        self.assertNotIn(self.delegated["token"], encoded)
        self.assertNotIn(self.delegated["username"], encoded)
        self.assertEqual(await self.sessions.get_user(8), self.delegated)
        another_worker = TerminalSessions(self.redis)
        self.assertEqual(await another_worker.get_user(8), self.delegated)
        self.assertEqual(self.redis.expires["ctf:terminal:user:8"], 1200)
        self.redis.now = 1200
        self.assertIsNone(await self.sessions.get_user(8))

    async def test_wrong_key_or_corrupt_ciphertext_does_not_return_secret(self):
        await self.sessions.remember_user(8, self.delegated)
        with patch("app.services.terminal_sessions.get_settings", return_value=SimpleNamespace(field_hmac_secret="other-key")):
            other_worker = TerminalSessions(self.redis)
        self.assertIsNone(await other_worker.get_user(8))
        self.redis.values["ctf:terminal:user:8"] = "invalid-ciphertext"
        self.assertIsNone(await self.sessions.get_user(8))

    async def test_ticket_is_hashed_in_redis_bound_to_run_and_consumed_once(self):
        ticket = await self.sessions.issue(101, 8)
        key = "ctf:terminal:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()
        self.assertIn(key, self.redis.values)
        self.assertNotIn(ticket, key)
        self.assertNotIn(self.delegated["token"], self.redis.values[key])
        self.assertEqual(self.redis.expires[key], 60)
        another_worker = TerminalSessions(self.redis)
        self.assertEqual(await another_worker.consume(ticket, 101), {"run_id": 101, "user_id": 8})
        self.assertIsNone(await self.sessions.consume(ticket, 101))
        self.assertNotIn(key, self.redis.values)

    async def test_ticket_wrong_run_or_expired_is_unusable(self):
        ticket = await self.sessions.issue(101, 8)
        self.assertIsNone(await self.sessions.consume(ticket, 102))
        self.assertIsNone(await self.sessions.consume(ticket, 101))
        expired = await self.sessions.issue(101, 8)
        self.redis.now = 60
        self.assertIsNone(await self.sessions.consume(expired, 101))
        self.assertIsNone(await self.sessions.consume(None, 101))

    async def test_protocol_is_stored_only_in_one_use_ticket(self):
        ticket = await self.sessions.issue(101, 8, "rdp")
        self.assertEqual(await self.sessions.consume(ticket, 101), {"run_id": 101, "user_id": 8, "protocol": "rdp"})
        self.assertIsNone(await self.sessions.consume(ticket, 101))
        with self.assertRaises(ValueError):
            await self.sessions.issue(101, 8, "vnc")

    async def test_attacker_target_is_stored_only_in_one_use_ticket(self):
        ticket = await self.sessions.issue(101, 8, "ssh", "attacker")
        self.assertEqual(await self.sessions.consume(ticket, 101), {
            "run_id": 101, "user_id": 8, "protocol": "ssh", "target": "attacker"
        })
        self.assertIsNone(await self.sessions.consume(ticket, 101))
        with self.assertRaises(ValueError):
            await self.sessions.issue(101, 8, None, "attacker")
        with self.assertRaises(ValueError):
            await self.sessions.issue(101, 8, "ssh", "other-host")

    async def test_oversized_ticket_is_rejected_before_redis_lookup(self):
        self.assertIsNone(await self.sessions.consume("a" * 129, 101))
        self.assertEqual(self.redis.getdel_calls, 0)

    async def test_closing_run_disconnects_only_its_tunnels_and_blocks_pending_tickets(self):
        target_socket, other_socket = AsyncMock(), AsyncMock()
        self.sessions.connections = {101: {target_socket}, 102: {other_socket}}
        ticket = await self.sessions.issue(101, 8)
        await self.sessions.close_run(101)
        target_socket.close.assert_awaited_once_with(code=1000)
        other_socket.close.assert_not_awaited()
        self.assertTrue(await self.sessions.is_closed(101))
        self.assertFalse(await self.sessions.is_closed(102))
        self.assertEqual(self.redis.expires["ctf:terminal:closed:101"], 86400)
        self.assertIsNone(await self.sessions.consume(ticket, 101))
        with self.assertRaises(ValueError):
            await self.sessions.issue(101, 8)
        other_ticket = await self.sessions.issue(102, 8)
        self.assertEqual(await self.sessions.consume(other_ticket, 102), {"run_id": 102, "user_id": 8})

    async def test_close_tombstone_is_seen_from_another_worker(self):
        another_worker = TerminalSessions(self.redis)
        await self.sessions.close_run(101)
        self.assertTrue(await another_worker.is_closed(101))
        with self.assertRaises(ValueError):
            await another_worker.issue(101, 8)

    async def test_forget_user_removes_only_that_personal_session(self):
        await self.sessions.remember_user(8, self.delegated)
        await self.sessions.remember_user(9, {**self.delegated, "username": "other-test"})
        await self.sessions.forget_user(8)
        self.assertIsNone(await self.sessions.get_user(8))
        self.assertEqual((await self.sessions.get_user(9))["username"], "other-test")

    async def test_shutdown_disconnects_all_live_tunnels(self):
        first, second = AsyncMock(), AsyncMock()
        self.sessions.connections = {101: {first}, 102: {second}}
        await self.sessions.shutdown()
        first.close.assert_awaited_once_with(code=1001)
        second.close.assert_awaited_once_with(code=1001)


if __name__ == "__main__":
    unittest.main()
