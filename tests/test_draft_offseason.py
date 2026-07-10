"""웹 시즌 종료에서 사용자 드래프트로 이어지는 상태 전환 검증."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web.backend.draft_management as draft_management
import web.backend.main as main


class FakePostseasonRunner:
    champion = None

    def __init__(self, *_args, **_kwargs):
        pass

    def run(self):
        return SimpleNamespace(rounds=[], champion=self.champion)


class TestDraftOffseasonLifecycle(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        response = self.client.post(
            "/api/game/new", json={"tid": "KIA", "seed": 314159})
        self.assertEqual(response.status_code, 200)
        FakePostseasonRunner.champion = main.SESSION.teams[0]

    def test_season_end_pauses_then_new_season_starts_after_pick(self):
        session = main.SESSION
        removed = session.user_team.roster[-1]

        def fake_aging(_rng, _teams, year, draft_mode):
            self.assertTrue(draft_mode)
            self.assertEqual(year, 1)
            session.user_team.roster.remove(removed)
            return SimpleNamespace(retired=[(session.user_team, removed)])

        fake_trades = SimpleNamespace(trades=[])
        fake_fa = SimpleNamespace(moved=[], signings=[], declared=0)
        fake_finance = SimpleNamespace(cap=200.0, tax_payers=[])

        with patch.object(draft_management, "PostseasonRunner", FakePostseasonRunner), \
             patch.object(draft_management, "offseason_tick", side_effect=fake_aging), \
             patch.object(draft_management, "run_trades", return_value=fake_trades), \
             patch.object(draft_management, "run_fa_market", return_value=fake_fa), \
             patch.object(draft_management, "offseason_finance_tick",
                          return_value=fake_finance):
            session._season_end()

            self.assertEqual(session.year, 1)
            self.assertIsNotNone(session.draft_session)
            self.assertTrue(session.draft_session.user_turn)
            self.assertEqual(len(session.user_team.roster), 24)
            self.assertEqual(
                [report["stage"] for report in session.offseason_reports],
                ["에이징/은퇴", "트레이드", "FA"])
            with self.assertRaisesRegex(RuntimeError, "드래프트"):
                session.advance("day")

            state = session.draft_state()
            selected = state["candidates"][0]
            result = session.draft_pick(selected["pid"])

        self.assertTrue(result["season_started"])
        self.assertEqual(session.year, 2)
        self.assertIsNone(session.draft_session)
        self.assertEqual(session.season.day, 0)
        self.assertEqual(len(session.user_team.roster), 25)
        self.assertEqual(
            [report["stage"] for report in session.offseason_reports],
            ["에이징/은퇴", "트레이드", "FA", "드래프트", "재정"])
        self.assertEqual(session.last_draft_state["complete"], True)


if __name__ == "__main__":
    unittest.main()
