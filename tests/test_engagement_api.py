"""구단주 이벤트 API·진행 차단·저장 호환 검증."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from web.backend.session import SAVE_DIR


class TestEngagementApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def new_game(self):
        response = self.client.post(
            "/api/game/new", json={"tid": "KIA", "seed": 20260711})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_endpoint_requires_game(self):
        self.assertEqual(self.client.get("/api/engagement").status_code, 404)

    def test_new_game_has_no_pending_event(self):
        self.new_game()
        body = self.client.get("/api/engagement").json()
        self.assertIsNone(body["pending_event"])
        self.assertEqual(body["front_office_points"], 0)
        self.assertEqual(body["achievement_count"], 0)

    def test_season_end_stops_at_first_owner_event(self):
        self.new_game()
        response = self.client.post("/api/sim/advance", json={"unit": "season_end"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["played_days"], 24)
        self.assertEqual(response.json()["state"]["day"], 24)
        event = self.client.get("/api/engagement").json()["pending_event"]
        self.assertEqual(event["milestone"], 24)

    def test_pending_event_blocks_progress_and_live_game(self):
        self.new_game()
        self.client.post("/api/sim/advance", json={"unit": "season_end"})
        blocked = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("구단주 이벤트", blocked.json()["detail"])
        live = self.client.post("/api/live/start")
        self.assertEqual(live.status_code, 409)

    def test_choice_resolves_event_and_updates_state(self):
        self.new_game()
        self.client.post("/api/sim/advance", json={"unit": "season_end"})
        before_budget = main.SESSION.user_team.budget
        response = self.client.post(
            "/api/engagement/choice", json={"choice_id": "results"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body["state"]["pending_event"])
        self.assertEqual(body["state"]["front_office_points"], 1)
        self.assertEqual(body["state"]["achievement_count"], 1)
        self.assertEqual(main.SESSION.user_team.budget, before_budget + 8.0)
        # 선택 효과 +6억, 첫 이사회 업적 +2억
        progressed = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(progressed.status_code, 200, progressed.text)

    def test_invalid_choice_returns_422(self):
        self.new_game()
        self.client.post("/api/sim/advance", json={"unit": "season_end"})
        response = self.client.post(
            "/api/engagement/choice", json={"choice_id": "invalid"})
        self.assertEqual(response.status_code, 422)

    def test_pending_event_survives_save_and_load(self):
        self.new_game()
        self.client.post("/api/sim/advance", json={"unit": "season_end"})
        before = self.client.get("/api/engagement").json()["pending_event"]
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        after = self.client.get("/api/engagement").json()["pending_event"]
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["choices"], before["choices"])

    def test_old_save_without_engagement_fields_is_migrated(self):
        self.new_game()
        for name in ("pending_owner_event", "issued_owner_events",
                     "owner_event_history", "front_office_points",
                     "achievements", "rewarded_seasons"):
            delattr(main.SESSION, name)
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        body = self.client.get("/api/engagement").json()
        self.assertEqual(body["front_office_points"], 0)
        self.assertEqual(body["achievement_count"], 0)


if __name__ == "__main__":
    unittest.main()
