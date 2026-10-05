"""El servidor es la autoridad de los puestos y del desempate temporal."""

from datetime import datetime, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, ChallengeCompletion, User
from app.services.bootstrap import ranking_rows


class AsyncSessionAdapter:
    def __init__(self, engine):
        self.session = Session(engine)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    async def execute(self, statement):
        return self.session.execute(statement)


class RankingOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_equal_points_favor_first_to_reach_current_score(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                session.add_all([
                    User(id=1, username="alice", password_hash="test", role="player", is_active=True),
                    User(id=2, username="bob", password_hash="test", role="player", is_active=True),
                    User(id=3, username="carol", password_hash="test", role="player", is_active=True),
                    User(id=4, username="inactive", password_hash="test", role="player", is_active=False),
                    User(id=5, username="dave", password_hash="test", role="player", is_active=True),
                ])
                at = lambda hour: datetime(2026, 10, 2, hour, tzinfo=timezone.utc)
                session.add_all([
                    ChallengeCompletion(user_id=1, challenge_id=1, awarded_points=100, completed_at=at(8)),
                    ChallengeCompletion(user_id=1, challenge_id=2, awarded_points=100, completed_at=at(12)),
                    ChallengeCompletion(user_id=2, challenge_id=1, awarded_points=100, completed_at=at(9)),
                    ChallengeCompletion(user_id=2, challenge_id=2, awarded_points=100, completed_at=at(11)),
                    ChallengeCompletion(user_id=4, challenge_id=1, awarded_points=1000, completed_at=at(7)),
                    ChallengeCompletion(user_id=5, challenge_id=1, awarded_points=300, completed_at=at(13)),
                ])
                session.commit()

            rows = await ranking_rows(lambda: AsyncSessionAdapter(engine))
            self.assertEqual([row["username"] for row in rows], ["dave", "bob", "alice", "carol"])
            self.assertEqual([row["position"] for row in rows], [1, 2, 3, 4])
            self.assertEqual([row["total_points"] for row in rows], [300, 200, 200, 0])
            self.assertEqual([row["challenges_completed"] for row in rows], [1, 2, 2, 0])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
