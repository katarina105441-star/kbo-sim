"""웹 시즌 종료에서 육성·트레이드·FA·드래프트로 이어지는 상태 전환 검증."""
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


class EmptyTradeMarket:
    def __init__(self, *_args, **_kwargs):
        self.complete = False
        self.report = SimpleNamespace(trades=[])
        self.user_trades = []

    def finish(self):
        self.complete = True
        return {"status": "complete", "message": "종료", "user_trades": 0}

    def state(self):
        return {"active": not self.complete, "complete": self.complete,
                "ai_trades": [], "user_trades": []}


class EmptyFAMarket:
    def __init__(self, *_args, **_kwargs):
        self.complete = True
        self.report = SimpleNamespace(moved=[], signings=[], declared=0, released=[])

    def state(self):
        return {"active": False, "complete": True, "results": [], "released": []}


class TestDraftOffseasonLifecycle(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        response = self.client.post(
            "/api/game/new", json={"tid": "KIA", "seed": 314159})
        self.assertEqual(response.status_code, 200)
        FakePostseasonRunner.champion = main.SESSION.teams[0]

    def test_season_end_pauses_at_trade_then_advances_to_draft(self):
        session = main.SESSION
        removed = session.user_team.lineup[0][0]

        def fake_aging(_rng, _teams, year, draft_mode):
            self.assertTrue(draft_mode)
            self.assertEqual(year, 1)
            session.user_team.roster.remove(removed)
            return SimpleNamespace(retired=[(session.user_team, removed)])

        fake_finance = SimpleNamespace(cap=200.0, tax_payers=[])

        with patch.object(draft_management, "PostseasonRunner", FakePostseasonRunner), \
             patch.object(draft_management, "offseason_tick", side_effect=fake_aging), \
             patch.object(draft_management, "InteractiveTradeMarket", EmptyTradeMarket), \
             patch.object(draft_management, "InteractiveFAMarket", EmptyFAMarket), \
             patch.object(draft_management, "offseason_finance_tick",
                          return_value=fake_finance):
            session._season_end()

            self.assertEqual(session.year, 1)
            self.assertIsNotNone(session.trade_session)
            self.assertIsNone(session.fa_session)
            self.assertIsNone(session.draft_session)
            self.assertEqual(len(session.user_team.roster), 24)
            self.assertEqual(
                [report["stage"] for report in session.offseason_reports],
                ["2군 육성", "에이징/은퇴"])
            with self.assertRaisesRegex(RuntimeError, "트레이드"):
                session.advance("day")

            transition = session.trade_finish()
            self.assertTrue(transition["trade_complete"])
            self.assertIsNone(session.trade_session)
            self.assertIsNone(session.fa_session)
            self.assertIsNotNone(session.draft_session)
            self.assertTrue(session.draft_session.user_turn)
            self.assertEqual(
                [report["stage"] for report in session.offseason_reports],
                ["2군 육성", "에이징/은퇴", "트레이드", "FA"])
            with self.assertRaisesRegex(RuntimeError, "드래프트"):
                session.advance("day")

            selected = session.draft_state()["candidates"][0]
            result = session.draft_pick(selected["pid"])

        self.assertTrue(result["season_started"])
        self.assertEqual(session.year, 2)
        self.assertIsNone(session.draft_session)
        self.assertEqual(session.season.day, 0)
        self.assertEqual(len(session.user_team.roster), 25)
        self.assertNotIn(removed, session.user_team.roster)
        self.assertNotIn(removed, [player for player, _slot in session.user_team.lineup])
        self.assertEqual(
            [report["stage"] for report in session.offseason_reports],
            ["2군 육성", "에이징/은퇴", "트레이드", "FA", "드래프트", "재정"])
        self.assertEqual(session.last_draft_state["complete"], True)


if __name__ == "__main__":
    unittest.main()
