"""ESC usa Guacamole para Kali, nunca para entregar la víctima al estudiante."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from app.models import Challenge, Laboratory, StudentGroup, User, VMAsset
from app.services.challenge_runtime import (
    _guacamole_access_references,
    _sync_guacamole_group_permissions,
    _sync_player_guacamole_permissions,
)


class Rows:
    def __init__(self, values):
        self.values = values

    def unique(self):
        return self

    def all(self):
        return self.values


class Session:
    def __init__(self, challenge, vms, labs):
        self.rows = iter(([challenge], vms, labs))
        self.queries = []
        self.user = SimpleNamespace(id=7, username="student-fixture", role="player")
        self.group = SimpleNamespace(id=3, code="GROUP", guacamole_group_identifier="GROUP")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, model, identifier):
        return self.user if model is User else self.group if model is StudentGroup else None

    async def scalars(self, statement):
        self.queries.append(statement)
        return Rows(next(self.rows))


class EscPermissionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.challenge = Challenge(
            id=9, code="ESC-01-RECON", is_published=True,
            asset_references=["LAB-LNXVICT", "LAB-KALI"],
        )
        self.vms = [
            SimpleNamespace(name="LAB-LNXVICT", ip_address="192.168.146.137",
                            guacamole_connection_id="victim-ssh", laboratory_id=2),
            SimpleNamespace(name="LAB-KALI", ip_address="192.168.146.134",
                            guacamole_connection_id="kali-ssh", laboratory_id=1),
        ]
        self.connections = [
            SimpleNamespace(identifier="victim-ssh", hostname="192.168.146.137", protocol="ssh"),
            SimpleNamespace(identifier="kali-ssh", hostname="192.168.146.134", protocol="ssh"),
        ]
        self.labs = [SimpleNamespace(id=1, code="LAB-ATACANTES", name="Atacantes"),
                     SimpleNamespace(id=2, code="LAB-VICTIMAS", name="Víctimas")]
        self.guac = SimpleNamespace(
            list_connections=AsyncMock(return_value=self.connections),
            patch_user_permissions=AsyncMock(),
            get_user_group_permissions=AsyncMock(return_value={"connectionPermissions": {}}),
            patch_user_group_permissions=AsyncMock(),
        )

    def request(self, session):
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            session_factory=lambda: session, guacamole_admin=self.guac,
        )))

    async def test_player_sync_grants_only_kali_and_queries_published_challenges(self):
        session = Session(self.challenge, self.vms, self.labs)
        await _sync_player_guacamole_permissions(self.request(session), 7)
        self.assertEqual(self.guac.patch_user_permissions.await_args.kwargs["connection_permissions"],
                         {"kali-ssh": ["READ"]})
        self.assertIn("is_published IS true", str(session.queries[0]))

    async def test_group_sync_grants_only_kali_and_queries_published_challenges(self):
        session = Session(self.challenge, self.vms, self.labs)
        await _sync_guacamole_group_permissions(self.request(session), 3)
        self.assertEqual(self.guac.patch_user_group_permissions.await_args.kwargs["connection_permissions"],
                         {"kali-ssh": ["READ"]})
        self.assertIn("is_published IS true", str(session.queries[0]))

    def test_lab01_reference_policy_is_unchanged(self):
        lab = Challenge(code="LAB-01", asset_references=["LAB-LNXVICT"])
        self.assertEqual(_guacamole_access_references(lab), ["LAB-LNXVICT"])
        self.assertEqual(_guacamole_access_references(self.challenge), ["LAB-KALI"])


if __name__ == "__main__":
    unittest.main()
