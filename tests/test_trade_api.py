"""사용자 참여 트레이드 FastAPI 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.league.trade_session import InteractiveTradeMarket
from web.backend.session import SAVE_DIR


class TestTradeApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        response = self.client.post(
            "/api/game/new", json={"tid": "KIA", "seed": 20260711})
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def prepare_market(self):
        session = main.SESSION
        market = InteractiveTradeMarket(
            session.rng, session.teams, list(session.teams),
            session.year, session.user_tid)
        session.trade_session = market
        session.offseason_standings = list(session.teams)
        session.offseason_reports = []
        session.fa_session = None
        session.draft_session = None
        return market

    def test_state_and_favorable_proposal(self):
        market = self.prepare_market()
        state_response = self.client.get("/api/trade/state")
        self.assertEqual(state_response.status_code, 200, state_response.text)
        state = state_response.json()
        target = next(team for team in state["teams"] if team["picks"])
        give = next(asset for asset in state["user"]["picks"] if asset["round"] == 1)
        receive = max(target["picks"], key=lambda asset: asset["round"])

        response = self.client.post("/api/trade/propose", json={
            "other_tid": target["tid"],
            "give_asset_ids": [give["id"]],
            "receive_asset_ids": [receive["id"]],
        })

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(response.json()["result"]["status"],
                      ("accepted", "counter", "rejected"))
        self.assertEqual(response.json()["trade"]["user_tid"], market.user_tid)

    def test_invalid_asset_returns_422(self):
        self.prepare_market()
        state = self.client.get("/api/trade/state").json()
        target = state["teams"][0]
        receive = target["players"][0]["id"]
        response = self.client.post("/api/trade/propose", json={
            "other_tid": target["tid"],
            "give_asset_ids": ["P:not-found"],
            "receive_asset_ids": [receive],
        })
        self.assertEqual(response.status_code, 422)

    def test_active_market_blocks_season_advance(self):
        self.prepare_market()
        response = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("트레이드", response.json()["detail"])

    def test_market_state_survives_save_and_load(self):
        self.prepare_market()
        expected = self.client.get("/api/trade/state").json()
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        self.client.post("/api/trade/finish")
        self.assertEqual(self.client.post("/api/game/load").status_code, 200)
        restored = self.client.get("/api/trade/state")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), expected)

    def test_finish_transitions_to_next_offseason_stage(self):
        self.prepare_market()
        response = self.client.post("/api/trade/finish")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["trade_complete"])
        self.assertEqual(self.client.get("/api/trade/state").status_code, 404)
        next_active = (
            self.client.get("/api/fa/state").status_code == 200
            or self.client.get("/api/draft/state").status_code == 200
            or body["game_state"]["year"] >= 2
        )
        self.assertTrue(next_active)

    def test_counter_endpoints_require_pending_counter(self):
        self.prepare_market()
        self.assertEqual(
            self.client.post("/api/trade/accept-counter").status_code, 409)
        self.assertEqual(
            self.client.post("/api/trade/reject-counter").status_code, 409)

    def test_no_active_market_returns_404(self):
        self.assertEqual(self.client.get("/api/trade/state").status_code, 404)
        self.assertEqual(self.client.post("/api/trade/finish").status_code, 404)


if __name__ == "__main__":
    unittest.main()
