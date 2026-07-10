"""2군·육성 FastAPI 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from web.backend.session import SAVE_DIR


class TestDevelopmentApi(unittest.TestCase):
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

    def test_initial_state_has_active_and_minors(self):
        response = self.client.get("/api/development/state")
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertEqual(state["active_count"], 25)
        self.assertEqual(state["minor_count"], 5)
        self.assertEqual(len(state["minors"]), 5)

    def test_promote_focus_and_demote(self):
        state = self.client.get("/api/development/state").json()
        player = state["minors"][0]
        focus = "control" if player["pos"] in ("SP", "RP", "CL") else "power"

        focus_response = self.client.put("/api/development/focus", json={
            "pid": player["pid"], "focus": focus,
        })
        self.assertEqual(focus_response.status_code, 200, focus_response.text)
        self.assertEqual(focus_response.json()["result"]["player"]["focus"], focus)

        promoted = self.client.post(
            "/api/development/promote", json={"pid": player["pid"]})
        self.assertEqual(promoted.status_code, 200, promoted.text)
        self.assertEqual(promoted.json()["development"]["active_count"], 26)

        demoted = self.client.post(
            "/api/development/demote", json={"pid": player["pid"]})
        self.assertEqual(demoted.status_code, 200, demoted.text)
        self.assertEqual(demoted.json()["development"]["active_count"], 25)

    def test_invalid_focus_returns_422(self):
        state = self.client.get("/api/development/state").json()
        player = state["minors"][0]
        response = self.client.put("/api/development/focus", json={
            "pid": player["pid"], "focus": "invalid",
        })
        self.assertEqual(response.status_code, 422)

    def test_day_advance_accrues_minor_days(self):
        before = self.client.get("/api/development/state").json()
        self.assertTrue(all(p["minor_days"] == 0 for p in before["minors"]))
        advance = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(advance.status_code, 200, advance.text)
        after = self.client.get("/api/development/state").json()
        self.assertTrue(all(p["minor_days"] == 1 for p in after["minors"]))

    def test_save_load_restores_focus_and_minor_days(self):
        state = self.client.get("/api/development/state").json()
        player = state["minors"][0]
        focus = "control" if player["pos"] in ("SP", "RP", "CL") else "power"
        self.client.put("/api/development/focus", json={
            "pid": player["pid"], "focus": focus,
        })
        self.client.post("/api/sim/advance", json={"unit": "day"})
        expected = self.client.get("/api/development/state").json()
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(self.client.post("/api/game/load").status_code, 200)
        restored = self.client.get("/api/development/state").json()
        self.assertEqual(restored, expected)

    def test_minor_player_detail_is_available(self):
        state = self.client.get("/api/development/state").json()
        pid = state["minors"][0]["pid"]
        response = self.client.get(f"/api/players/{pid}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["pid"], pid)

    def test_auto_roster_keeps_25_active(self):
        state = self.client.get("/api/development/state").json()
        self.client.post("/api/development/promote", json={"pid": state["minors"][0]["pid"]})
        response = self.client.post("/api/development/auto")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["development"]["active_count"], 25)


if __name__ == "__main__":
    unittest.main()
