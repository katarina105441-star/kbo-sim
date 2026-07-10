"""프런트 평가 API·세션 저장 호환 검증."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.league.front_office import evaluate_season
from web.backend.session import SAVE_DIR


class TestFrontOfficeApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def new_game(self, tid="KIA"):
        response = self.client.post("/api/game/new", json={"tid": tid, "seed": 20260711})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_front_office_endpoint_requires_game(self):
        response = self.client.get("/api/front-office")
        self.assertEqual(response.status_code, 404)

    def test_new_game_creates_objective_and_confidence(self):
        self.new_game("KIA")
        response = self.client.get("/api/front-office")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["objective"]["year"], 1)
        self.assertEqual(body["owner_confidence"], 65.0)
        self.assertIn(body["progress"], {"ahead", "on_track", "behind"})
        self.assertEqual(body["career"]["seasons"], 0)

    def test_rebuild_team_receives_looser_initial_goal(self):
        self.new_game("SAM")
        rebuild_target = self.client.get("/api/front-office").json()["objective"]["target_rank"]
        main.SESSION = None
        self.new_game("KIA")
        contender_target = self.client.get("/api/front-office").json()["objective"]["target_rank"]
        self.assertGreater(rebuild_target, contender_target)

    def test_evaluation_is_exposed_in_history(self):
        self.new_game("KT")
        session = main.SESSION
        target = session.current_objective.target_rank
        evaluate_season(session, {
            "my_rank": target,
            "my_record": "72승 5무 67패",
            "champion": "다른 팀",
        })
        body = self.client.get("/api/front-office").json()
        self.assertEqual(body["career"]["seasons"], 1)
        self.assertTrue(body["latest_evaluation"]["goal_met"])
        self.assertEqual(body["latest_evaluation"]["target_rank"], target)

    def test_save_load_preserves_front_office_state(self):
        self.new_game("KT")
        session = main.SESSION
        evaluate_season(session, {
            "my_rank": 3,
            "my_record": "78승 4무 62패",
            "champion": "다른 팀",
        })
        before = self.client.get("/api/front-office").json()
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        after = self.client.get("/api/front-office").json()
        self.assertEqual(after["owner_confidence"], before["owner_confidence"])
        self.assertEqual(after["history"], before["history"])

    def test_old_save_without_front_office_fields_is_migrated(self):
        self.new_game("LTE")
        delattr(main.SESSION, "owner_confidence")
        delattr(main.SESSION, "front_office_history")
        delattr(main.SESSION, "current_objective")
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        body = self.client.get("/api/front-office").json()
        self.assertEqual(body["owner_confidence"], 65.0)
        self.assertEqual(body["career"]["seasons"], 0)
        self.assertEqual(body["objective"]["year"], 1)


if __name__ == "__main__":
    unittest.main()
