"""실시간 경기 FastAPI 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from web.backend.session import SAVE_DIR


class TestLiveApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        r = self.client.post("/api/game/new", json={"tid": "KIA", "seed": 42})
        self.assertEqual(r.status_code, 200)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def start(self):
        r = self.client.post("/api/live/start")
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_start_state_step_and_auto_complete(self):
        data = self.start()
        self.assertFalse(data["done"])
        self.assertEqual(data["state"]["inning"], 1)
        self.assertEqual(self.client.get("/api/game/state").json()["day"], 0)

        step = self.client.post("/api/live/step")
        self.assertEqual(step.status_code, 200)
        self.assertTrue(any(e["t"] == "pa" for e in step.json()["events"]))

        auto = self.client.post("/api/live/auto")
        self.assertEqual(auto.status_code, 200, auto.text)
        self.assertTrue(auto.json()["done"])
        self.assertIsNotNone(auto.json()["result"])
        self.assertEqual(self.client.get("/api/game/state").json()["day"], 1)
        results = self.client.get("/api/results?day=1").json()
        self.assertEqual(len(results["games"]), 5)
        mine = results["games"][data["meta"]["game_idx"]]
        self.assertFalse(mine.get("hidden", False))

    def test_advance_and_duplicate_start_are_blocked(self):
        self.start()
        duplicate = self.client.post("/api/live/start")
        self.assertEqual(duplicate.status_code, 409)
        advance = self.client.post("/api/sim/advance", json={"unit": "day"})
        self.assertEqual(advance.status_code, 409)

    def test_manual_pitcher_change(self):
        data = self.start()
        user_side = data["meta"]["user_side"]
        guard = 0
        while data["state"]["fielding_side"] != user_side:
            data = self.client.post("/api/live/step").json()
            guard += 1
            self.assertLess(guard, 50)
        pid = data["state"]["available_relievers"][0]["pid"]
        changed = self.client.post("/api/live/pitcher", json={"pid": pid})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["state"]["pitcher"]["pid"], pid)
        step = self.client.post("/api/live/step").json()
        pa = next(e for e in step["events"] if e["t"] == "pa")
        self.assertEqual(pa["pitcher"]["pid"], pid)

    def test_live_state_without_game_returns_404(self):
        self.assertEqual(self.client.get("/api/live/state").status_code, 404)
        self.assertEqual(self.client.post("/api/live/step").status_code, 404)

    def test_pending_live_game_can_be_saved_and_loaded(self):
        before = self.start()
        for _ in range(5):
            before = self.client.post("/api/live/step").json()
        saved_state = before["state"]
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)

        # 메모리 상태를 진행시킨 뒤 저장본을 복원해 커서가 돌아오는지 확인한다.
        self.client.post("/api/live/step")
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200)
        restored = self.client.get("/api/live/state")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["state"], saved_state)


if __name__ == "__main__":
    unittest.main()
