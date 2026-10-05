"""Editar recursos no invalida flags ni destruye los hashes históricos del run."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from app.api.challenges import archive_challenge, create_flag, require_idle_challenge, update_flag
from app.schemas import FlagUpdate
from app.services.runtime_flags import EXPLICIT_STATIC_VALIDATOR


class ChallengeEditSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_challenge_allows_runtime_changes(self):
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))
        await require_idle_challenge(session, 1)

    async def test_active_even_expired_pending_cleanup_blocks_runtime_changes(self):
        session = SimpleNamespace(scalar=AsyncMock(return_value=101))
        with self.assertRaises(HTTPException) as error:
            await require_idle_challenge(session, 1)
        self.assertEqual(error.exception.status_code, 409)

    async def test_archive_does_not_interrupt_active_run(self):
        challenge = SimpleNamespace(id=7, is_published=True)
        session, request = self.setup_edit([challenge, 101])
        with self.assertRaises(HTTPException) as error:
            await archive_challenge("OLD-01", request, SimpleNamespace(id=1))
        self.assertEqual(error.exception.status_code, 409)
        self.assertTrue(challenge.is_published)
        session.commit.assert_not_called()

    async def test_archive_preserves_challenge_row_when_idle(self):
        challenge = SimpleNamespace(id=7, is_published=True)
        session, request = self.setup_edit([challenge, None])
        with patch("app.api.challenges.write_audit", new_callable=AsyncMock):
            await archive_challenge("OLD-01", request, SimpleNamespace(id=1))
        self.assertFalse(challenge.is_published)
        session.delete.assert_not_called()
        session.commit.assert_awaited_once()

    def setup_edit(self, scalar_results):
        session = AsyncMock()
        session.add = Mock()
        session.scalar.side_effect = scalar_results
        context = AsyncMock()
        context.__aenter__.return_value = session
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=lambda: context)))
        return session, request

    async def test_label_only_edit_preserves_run_hashes_without_deletes(self):
        flag = SimpleNamespace(id=11, flag_order=1, is_active=True, mode="dynamic", template="FLAG{example_{{RAND}}}", flag_hash=None, label="Old")
        challenge = SimpleNamespace(id=1, flags=[flag])
        session, request = self.setup_edit([challenge])
        payload = FlagUpdate(label="New label", flag_order=1, is_active=True, mode="dynamic", template=flag.template)
        with patch("app.api.challenges.write_audit", new_callable=AsyncMock), patch("app.api.challenges.challenge_view", return_value={"ok": True}):
            await update_flag("LAB-01", 11, payload, request, SimpleNamespace(id=1))
        session.execute.assert_not_called()
        session.commit.assert_awaited_once()
        self.assertEqual(flag.label, "New label")
        self.assertEqual(session.scalar.await_count, 1)

    async def test_changing_dynamic_order_during_active_run_is_rejected_without_mutation(self):
        flag = SimpleNamespace(id=11, flag_order=1, is_active=True, mode="dynamic", template="FLAG{example_{{RAND}}}", flag_hash=None, label="Old")
        session, request = self.setup_edit([SimpleNamespace(id=1, flags=[flag]), 101])
        payload = FlagUpdate(label="New label", flag_order=2, is_active=True, mode="dynamic", template=flag.template)
        with self.assertRaises(HTTPException) as error:
            await update_flag("LAB-01", 11, payload, request, SimpleNamespace(id=1))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(flag.flag_order, 1)
        self.assertEqual(flag.label, "Old")
        session.execute.assert_not_called()
        session.commit.assert_not_called()

    async def test_dynamic_to_static_requires_a_new_value(self):
        flag = SimpleNamespace(id=11, flag_order=1, is_active=True, mode="dynamic", template="FLAG{run_{{RAND}}}", flag_hash=None, validator="exact_hash", label="Old")
        session, request = self.setup_edit([SimpleNamespace(id=1, flags=[flag])])
        payload = FlagUpdate(label="Old", flag_order=1, is_active=True, mode="static")
        with self.assertRaises(HTTPException) as error:
            await update_flag("LAB-01", 11, payload, request, SimpleNamespace(id=1))
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(flag.mode, "dynamic")
        session.commit.assert_not_called()

    async def test_explicit_static_lab01_update_marks_existing_column(self):
        flag = SimpleNamespace(id=11, flag_order=1, is_active=True, mode="static", template=None, flag_hash="old-hash", validator="exact_hash", label="Old")
        session, request = self.setup_edit([SimpleNamespace(id=1, flags=[flag]), None])
        payload = FlagUpdate(label="Old", flag_order=1, is_active=True, mode="static", value="FLAG{new_static_test}")
        with patch("app.api.challenges.write_audit", new_callable=AsyncMock), patch("app.api.challenges.challenge_view", return_value={"ok": True}), patch("app.api.challenges.hash_password", return_value="new-hash"):
            await update_flag("LAB-01", 11, payload, request, SimpleNamespace(id=1))
        self.assertEqual(flag.flag_hash, "new-hash")
        self.assertEqual(flag.validator, EXPLICIT_STATIC_VALIDATOR)
        session.commit.assert_awaited_once()

    async def test_static_flag_creation_marks_existing_column(self):
        challenge = SimpleNamespace(id=1, flags=[])
        session, request = self.setup_edit([challenge, None])
        payload = FlagUpdate(label="Evidence", flag_order=1, is_active=True, mode="static", value="FLAG{static_test}")
        with patch("app.api.challenges.write_audit", new_callable=AsyncMock), patch("app.api.challenges.challenge_view", return_value={"ok": True}), patch("app.api.challenges.hash_password", return_value="stored-hash"):
            await create_flag("NEW-01", payload, request, SimpleNamespace(id=1))
        created = session.add.call_args.args[0]
        self.assertEqual(created.flag_hash, "stored-hash")
        self.assertEqual(created.validator, EXPLICIT_STATIC_VALIDATOR)
        session.commit.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
