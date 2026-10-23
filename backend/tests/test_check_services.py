"""Contrato del indicador de salud: fallos y timeouts no filtran secretos."""
import asyncio
import contextlib
import io
import unittest
from unittest.mock import AsyncMock, patch

from app import check_services as health


class HealthChecks(unittest.IsolatedAsyncioTestCase):
    async def test_success_requires_both_services(self):
        with patch.object(health, "check_postgres", AsyncMock()), patch.object(health, "check_redis", AsyncMock()):
            self.assertTrue(all((await health.run_checks()).values()))

    async def test_each_dependency_can_fail_independently(self):
        for failed in ("check_postgres", "check_redis"):
            with self.subTest(failed=failed), patch.object(health, "check_postgres", AsyncMock()), patch.object(health, "check_redis", AsyncMock()):
                getattr(health, failed).side_effect = RuntimeError("private-connection-url")
                values = list((await health.run_checks()).values())
                self.assertEqual(values.count(False), 1)

    async def test_timeout_is_unhealthy(self):
        async def hanging():
            await asyncio.sleep(60)
        self.assertEqual(await health.probe("test", hanging, timeout=.01), ("test", False))

    async def test_http_failure_marks_check_unhealthy(self):
        with patch.object(health, "check_postgres", AsyncMock()), patch.object(health, "check_redis", AsyncMock()), patch.object(health, "check_http", side_effect=OSError("unavailable")):
            results = await health.run_checks(True)
            self.assertFalse(results["API HTTP"])
            self.assertTrue(results["Redis (PING)"])


class HealthCommand(unittest.TestCase):
    def test_exit_code_and_secret_redaction(self):
        output = io.StringIO()
        with patch.object(health, "check_postgres", AsyncMock(side_effect=RuntimeError("postgresql://secret:private@host/db"))), patch.object(health, "check_redis", AsyncMock()), contextlib.redirect_stdout(output):
            self.assertEqual(health.main([]), 1)
        self.assertNotIn("secret", output.getvalue())
        self.assertNotIn("private", output.getvalue())
        self.assertIn("Redis (PING): OK", output.getvalue())

    def test_success_exit(self):
        with patch.object(health, "run_checks", AsyncMock(return_value={"PostgreSQL": True, "Redis": True})), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(health.main([]), 0)


if __name__ == "__main__":
    unittest.main()
