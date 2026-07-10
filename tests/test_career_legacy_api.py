"""감독 은퇴 API·진행 차단·저장 복원 검증."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from web.backend.session import SAVE_DIR


class TestCareerLegacyApi(unittest.TestCase):
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

    def seed_history(self, seasons=10, championships=1):
        session = main.SESSION
        session.front_office_history = []
        for year in range(1, seasons + 1):
            champion = year <= championships
            session.front_office_history.append({
                "year": year,
                "actual_rank": 1 if champion else 5,
                "target_rank": 5,
                "record": "75승 3무 66패",
                "champion": champion,
                "goal_met": True,
                "grade": "S" if champion else "B",
                "dismissed": False,
            })
        session.year = seasons
        return session

    def test_endpoint_requires_game(self):
        self.assertEqual(self.client.get("/api/career").status_code, 404)

    def test_new_game_is_not_retirement_eligible(self):
        self.new_game()
        body = self.client.get("/api/career").json()
        self.assertFalse(body["retirement_eligible"])
        self.assertEqual(body["retirement_min_seasons"], 10)
        self.assertEqual(body["retirement_mandatory_seasons"], 30)
        self.assertEqual(body["legacy_preview"]["totals"]["seasons"], 0)

    def test_early_retirement_returns_422(self):
        self.new_game()
        response = self.client.post("/api/career/retire")
        self.assertEqual(response.status_code, 422)
        self.assertIn("10시즌", response.json()["detail"])

    def test_voluntary_retirement_returns_final_summary(self):
        self.new_game()
        self.seed_history(seasons=10, championships=1)
        response = self.client.post("/api/career/retire")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["career"]["status"], "retired")
        self.assertEqual(body["summary"]["totals"]["seasons"], 10)
        self.assertEqual(body["summary"]["reason"], "voluntary")
        self.assertIsNotNone(body["career"]["hall_of_fame"])

    def test_retired_career_blocks_progress_and_live_game(self):
        self.new_game()
        self.seed_history(seasons=10)
        self.client.post("/api/career/retire")
        advance = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(advance.status_code, 409)
        self.assertIn("은퇴", advance.json()["detail"])
        live = self.client.post("/api/live/start")
        self.assertEqual(live.status_code, 409)
        self.assertIn("은퇴", live.json()["detail"])

    def test_retirement_cannot_be_repeated(self):
        self.new_game()
        self.seed_history(seasons=10)
        self.assertEqual(self.client.post("/api/career/retire").status_code, 200)
        second = self.client.post("/api/career/retire")
        self.assertEqual(second.status_code, 409)

    def test_retirement_summary_survives_save_and_load(self):
        self.new_game()
        self.seed_history(seasons=12, championships=2)
        retired = self.client.post("/api/career/retire").json()["summary"]
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        career = self.client.get("/api/career").json()
        self.assertEqual(career["status"], "retired")
        self.assertEqual(career["retirement_summary"], retired)
        self.assertEqual(career["hall_of_fame"]["score"], retired["score"])

    def test_old_save_without_legacy_fields_is_migrated(self):
        self.new_game()
        for name in ("retirement_summary", "hall_of_fame",
                     "retirement_year", "retirement_reason"):
            delattr(main.SESSION, name)
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        career = self.client.get("/api/career").json()
        self.assertIsNone(career["retirement_summary"])
        self.assertIsNone(career["hall_of_fame"])

    def test_retirement_finalizes_current_tenure(self):
        self.new_game()
        self.seed_history(seasons=10)
        self.client.post("/api/career/retire")
        career = self.client.get("/api/career").json()
        tenure = career["tenures"][-1]
        self.assertIsNotNone(tenure["end_year"])
        self.assertEqual(tenure["exit_reason"], "자발적 은퇴")


if __name__ == "__main__":
    unittest.main()
