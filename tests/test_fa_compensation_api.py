"""FA 보상선수 FastAPI 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.league.fa import FASigning
from kbo.league.fa_compensation import InteractiveFACompensation
from web.backend.session import SAVE_DIR


class TestFACompensationApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        response = self.client.post(
            "/api/game/new", json={"tid": "KIA", "seed": 20260711})
        self.assertEqual(response.status_code, 200, response.text)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def prepare_case(self, user_acquires=False, grade="A"):
        session = main.SESSION
        by_tid = {team.tid: team for team in session.teams}
        home = by_tid["LG"] if user_acquires else by_tid["KIA"]
        destination = by_tid["KIA"] if user_acquires else by_tid["LG"]
        player = max(home.roster, key=lambda p: p.contract.salary)
        old_salary = max(1.0, player.contract.salary)
        comp = round(old_salary * ({"A": 3.0, "B": 2.0, "C": 1.5}[grade]), 2)
        home.roster.remove(player)
        destination.roster.append(player)
        player.team_id = destination.tid
        destination.budget = round(destination.budget - comp, 2)
        home.budget = round(home.budget + comp, 2)
        signing = FASigning(player, home.tid, destination.tid, grade,
                            old_salary * 1.2, old_salary, comp, 2,
                            (0.4, 0.3, 0.3))
        session.compensation_session = InteractiveFACompensation(
            session.teams, [signing], session.year, session.user_tid)
        session.offseason_standings = list(session.teams)
        session.offseason_reports = []
        return signing

    def test_user_losing_team_can_choose_cash(self):
        self.prepare_case(user_acquires=False)
        state = self.client.get("/api/fa/compensation/state")
        self.assertEqual(state.status_code, 200, state.text)
        self.assertEqual(state.json()["mode"], "select")
        response = self.client.post("/api/fa/compensation/cash")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["compensation_complete"])
        self.assertEqual(response.json()["result"]["kind"], "cash")
        self.assertEqual(self.client.get("/api/fa/compensation/state").status_code, 404)

    def test_user_can_select_compensation_player(self):
        self.prepare_case(user_acquires=False)
        state = self.client.get("/api/fa/compensation/state").json()
        candidate = state["candidates"][0]
        response = self.client.post(
            "/api/fa/compensation/player", json={"pid": candidate["pid"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["player"]["pid"], candidate["pid"])

    def test_user_acquiring_team_submits_protection(self):
        self.prepare_case(user_acquires=True)
        state = self.client.get("/api/fa/compensation/state").json()
        self.assertEqual(state["mode"], "protect")
        bad = self.client.post("/api/fa/compensation/protect", json={"pids": []})
        self.assertEqual(bad.status_code, 422)
        response = self.client.post("/api/fa/compensation/protect", json={
            "pids": state["recommended_protected"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["compensation_complete"])

    def test_active_compensation_blocks_season_advance(self):
        self.prepare_case(user_acquires=False)
        response = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("보상선수", response.json()["detail"])

    def test_compensation_state_survives_save_and_load(self):
        self.prepare_case(user_acquires=True)
        expected = self.client.get("/api/fa/compensation/state").json()
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        self.client.post("/api/fa/compensation/protect-auto")
        self.assertEqual(self.client.post("/api/game/load").status_code, 200)
        restored = self.client.get("/api/fa/compensation/state")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json(), expected)

    def test_no_active_compensation_returns_404(self):
        self.assertEqual(self.client.get("/api/fa/compensation/state").status_code, 404)
        self.assertEqual(self.client.post("/api/fa/compensation/cash").status_code, 404)


if __name__ == "__main__":
    unittest.main()
