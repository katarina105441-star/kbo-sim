"""사용자 참여 FA 시장 FastAPI 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.league.fa_session import InteractiveFAMarket
from web.backend.session import SAVE_DIR


class TestFAApi(unittest.TestCase):
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
        market = InteractiveFAMarket(
            session.rng, session.teams, list(session.teams),
            session.year, session.user_tid)
        session.fa_session = market
        session.offseason_standings = list(session.teams)
        session.offseason_reports = []
        return market

    def test_state_offer_or_pass_advances_market(self):
        market = self.prepare_market()
        state = self.client.get("/api/fa/state")
        self.assertEqual(state.status_code, 200, state.text)
        before = state.json()
        self.assertEqual(before["player"]["pid"], market.pending.player.pid)

        if before["market"]["can_offer"]:
            aav = min(before["market"]["fair_aav"], before["market"]["max_offer"])
            response = self.client.post("/api/fa/offer", json={"aav": aav})
        else:
            response = self.client.post("/api/fa/pass")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["pid"], before["player"]["pid"])

    def test_invalid_offer_returns_422(self):
        self.prepare_market()
        state = self.client.get("/api/fa/state").json()
        response = self.client.post(
            "/api/fa/offer", json={"aav": state["market"]["max_offer"] + 100})
        self.assertEqual(response.status_code, 422)

    def test_active_market_blocks_season_advance(self):
        self.prepare_market()
        response = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("FA", response.json()["detail"])

    def test_market_state_survives_save_and_load(self):
        self.prepare_market()
        self.client.post("/api/fa/auto")
        expected = self.client.get("/api/fa/state").json()
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        self.client.post("/api/fa/auto")
        self.assertEqual(self.client.post("/api/game/load").status_code, 200)
        restored = self.client.get("/api/fa/state")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), expected)

    def test_auto_finish_starts_compensation_draft_or_new_season(self):
        self.prepare_market()
        response = self.client.post("/api/fa/auto-finish")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["fa_complete"])
        self.assertEqual(self.client.get("/api/fa/state").status_code, 404)
        compensation_active = body.get("compensation_active", False)
        draft_active = body.get("draft_active", False)
        self.assertTrue(compensation_active or draft_active or body["game_state"]["year"] >= 2)
        if compensation_active:
            self.assertEqual(self.client.get("/api/fa/compensation/state").status_code, 200)

    def test_no_active_market_returns_404(self):
        self.assertEqual(self.client.get("/api/fa/state").status_code, 404)
        self.assertEqual(self.client.post("/api/fa/pass").status_code, 404)


if __name__ == "__main__":
    unittest.main()
