"""사용자 참여 드래프트 FastAPI 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.league.draft_session import InteractiveDraft
from web.backend.session import SAVE_DIR


class TestDraftApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        response = self.client.post(
            "/api/game/new", json={"tid": "KIA", "seed": 20260710})
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def prepare_draft(self, holes=1):
        session = main.SESSION
        session.user_team.roster = session.user_team.roster[:-holes]
        session.offseason_reports = []
        draft = InteractiveDraft(
            session.rng, session.teams, list(session.teams),
            session.year, session.user_tid)
        draft.advance_to_user()
        session.draft_session = draft
        return draft

    def test_state_and_manual_pick_complete_to_new_season(self):
        self.prepare_draft(holes=1)
        state = self.client.get("/api/draft/state")
        self.assertEqual(state.status_code, 200, state.text)
        data = state.json()
        self.assertTrue(data["user_turn"])
        pid = data["candidates"][-1]["pid"]

        picked = self.client.post("/api/draft/pick", json={"pid": pid})

        self.assertEqual(picked.status_code, 200, picked.text)
        body = picked.json()
        self.assertEqual(body["selected"]["pid"], pid)
        self.assertTrue(body["season_started"])
        self.assertEqual(body["game_state"]["year"], 2)
        self.assertEqual(self.client.get("/api/draft/state").status_code, 404)
        self.assertEqual(len(main.SESSION.user_team.roster), 25)

    def test_auto_pick_uses_recommendation(self):
        self.prepare_draft(holes=1)
        state = self.client.get("/api/draft/state").json()
        recommended = next(
            candidate for candidate in state["candidates"]
            if candidate["recommended"])

        response = self.client.post("/api/draft/auto-pick")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["selected"]["pid"], recommended["pid"])

    def test_invalid_player_returns_422(self):
        self.prepare_draft(holes=1)
        response = self.client.post(
            "/api/draft/pick", json={"pid": "NOT-A-PROSPECT"})
        self.assertEqual(response.status_code, 422)

    def test_active_draft_blocks_season_advance(self):
        self.prepare_draft(holes=1)
        response = self.client.post(
            "/api/sim/advance", json={"unit": "day"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("드래프트", response.json()["detail"])

    def test_draft_state_survives_save_and_load(self):
        self.prepare_draft(holes=2)
        before = self.client.get("/api/draft/state").json()
        first = before["candidates"][0]["pid"]
        picked = self.client.post("/api/draft/pick", json={"pid": first})
        self.assertFalse(picked.json()["season_started"])
        expected = picked.json()["draft"]

        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        self.client.post("/api/draft/auto-pick")
        self.assertEqual(self.client.post("/api/game/load").status_code, 200)
        restored = self.client.get("/api/draft/state")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json(), expected)

    def test_no_active_draft_returns_404(self):
        self.assertEqual(self.client.get("/api/draft/state").status_code, 404)
        self.assertEqual(
            self.client.post("/api/draft/pick", json={"pid": "x"}).status_code,
            404)


if __name__ == "__main__":
    unittest.main()
