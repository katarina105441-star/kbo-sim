"""감독 커리어 API·진행 차단·재취업·저장 호환 검증."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.league.manager_career import process_season_career
from web.backend.session import SAVE_DIR


class TestManagerCareerApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def new_game(self, tid="KIA"):
        response = self.client.post(
            "/api/game/new", json={"tid": tid, "seed": 20260711})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def force_dismissal(self):
        session = main.SESSION
        session.owner_confidence = 10.0
        session.front_office_history = [{
            "year": session.year,
            "grade": "F",
            "goal_met": False,
            "champion": False,
            "target_rank": 3,
            "actual_rank": 10,
        }]
        session.offseason_standings = session.season.standings()
        session.trade_session = object()
        process_season_career(session)
        return session

    def test_endpoint_requires_game(self):
        self.assertEqual(self.client.get("/api/career").status_code, 404)

    def test_new_game_creates_career_profile(self):
        self.new_game()
        body = self.client.get("/api/career").json()
        self.assertEqual(body["status"], "employed")
        self.assertEqual(body["reputation"], 50.0)
        self.assertEqual(body["team"]["tid"], "KIA")
        self.assertEqual(len(body["tenures"]), 1)

    def test_dismissal_exposes_job_offers(self):
        self.new_game()
        self.force_dismissal()
        body = self.client.get("/api/career").json()
        self.assertEqual(body["status"], "dismissed")
        self.assertEqual(len(body["job_offers"]), 3)
        self.assertTrue(any(item["tone"] == "critical" for item in body["media_feed"]))

    def test_dismissal_blocks_progress_and_live_game(self):
        self.new_game()
        self.force_dismissal()
        advance = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(advance.status_code, 409)
        self.assertIn("재취업", advance.json()["detail"])
        live = self.client.post("/api/live/start")
        self.assertEqual(live.status_code, 409)
        self.assertIn("재취업", live.json()["detail"])

    def test_accept_offer_switches_user_team_and_resumes_offseason(self):
        self.new_game()
        session = self.force_dismissal()
        old_tid = session.user_tid
        offer = session.job_offers[0]
        response = self.client.post(
            "/api/career/accept", json={"tid": offer["tid"]})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["state"]["user_tid"], offer["tid"])
        self.assertEqual(body["career"]["status"], "employed")
        self.assertEqual(body["move"]["from_tid"], old_tid)
        self.assertIsNotNone(main.SESSION.trade_session)
        self.assertTrue(main.SESSION.user_team.user_managed)
        old_team = next(team for team in main.SESSION.teams if team.tid == old_tid)
        self.assertFalse(old_team.user_managed)

    def test_invalid_offer_returns_422(self):
        self.new_game()
        self.force_dismissal()
        response = self.client.post(
            "/api/career/accept", json={"tid": "INVALID"})
        self.assertEqual(response.status_code, 422)

    def test_accept_without_dismissal_returns_409(self):
        self.new_game()
        response = self.client.post(
            "/api/career/accept", json={"tid": "SAM"})
        self.assertEqual(response.status_code, 409)

    def test_dismissed_state_and_offers_survive_save_load(self):
        self.new_game()
        self.force_dismissal()
        before = self.client.get("/api/career").json()
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        after = self.client.get("/api/career").json()
        self.assertEqual(after["status"], "dismissed")
        self.assertEqual(after["job_offers"], before["job_offers"])
        self.assertEqual(after["media_feed"], before["media_feed"])

    def test_old_save_without_career_fields_is_migrated(self):
        self.new_game("KT")
        for name in ("career_status", "manager_reputation", "fan_approval",
                     "media_pressure", "job_offers", "career_moves",
                     "media_feed", "career_processed_years", "manager_tenures"):
            delattr(main.SESSION, name)
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        body = self.client.get("/api/career").json()
        self.assertEqual(body["status"], "employed")
        self.assertEqual(body["reputation"], 50.0)
        self.assertEqual(body["team"]["tid"], "KT")


if __name__ == "__main__":
    unittest.main()
