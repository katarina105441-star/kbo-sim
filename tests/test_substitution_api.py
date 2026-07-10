"""MVP-3 Part 2B 실시간 교체 API 통합 테스트."""
import os
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from web.backend.session import SAVE_DIR


class TestSubstitutionApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        r = self.client.post("/api/game/new", json={"tid": "KIA", "seed": 62026})
        self.assertEqual(r.status_code, 200)
        self.data = self.client.post("/api/live/start").json()

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def step_until(self, predicate, limit=250):
        data = self.data
        for _ in range(limit):
            if predicate(data):
                self.data = data
                return data
            data = self.client.post("/api/live/step").json()
            if data["done"]:
                break
        self.fail("요청한 실시간 경기 상태에 도달하지 못했습니다.")

    def test_pinch_hitter_endpoint_and_reentry_rejection(self):
        user = self.data["meta"]["user_side"]
        data = self.step_until(lambda d: d["state"]["batting_side"] == user)
        bench = data["state"]["batting_substitutions"]["bench"]
        first, second = bench[0]["pid"], bench[1]["pid"]

        r = self.client.post("/api/live/pinch-hitter", json={"pid": first})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["state"]["next_batter"]["pid"], first)
        self.assertEqual(r.json()["events"][0]["kind"], "pinch_hitter")
        self.client.post("/api/live/pinch-hitter", json={"pid": second})
        retry = self.client.post("/api/live/pinch-hitter", json={"pid": first})
        self.assertEqual(retry.status_code, 422)

    def test_pinch_runner_endpoint(self):
        user = self.data["meta"]["user_side"]
        data = self.step_until(
            lambda d: d["state"]["batting_side"] == user
            and bool(d["state"]["batting_substitutions"]["runners"]))
        subs = data["state"]["batting_substitutions"]
        runner = subs["runners"][0]
        bench = subs["bench"][0]
        r = self.client.post("/api/live/pinch-runner",
                             json={"base": runner["base"], "pid": bench["pid"]})
        self.assertEqual(r.status_code, 200, r.text)
        runners = r.json()["state"]["batting_substitutions"]["runners"]
        changed = next(x for x in runners if x["base"] == runner["base"])
        self.assertEqual(changed["pid"], bench["pid"])
        self.assertEqual(r.json()["events"][0]["kind"], "pinch_runner")

    def test_defensive_sub_endpoint_and_wrong_phase(self):
        user = self.data["meta"]["user_side"]
        data = self.step_until(lambda d: d["state"]["fielding_side"] == user)
        fld = data["state"]["fielding_substitutions"]
        choice = None
        for active in fld["lineup"]:
            if active["slot"] == "DH":
                continue
            candidate = next((p for p in fld["bench"] if p["pos"] == active["slot"]), None)
            if candidate:
                choice = active, candidate
                break
        self.assertIsNotNone(choice)
        active, candidate = choice
        r = self.client.post("/api/live/defense",
                             json={"out_pid": active["pid"], "in_pid": candidate["pid"]})
        self.assertEqual(r.status_code, 200, r.text)
        lineup = r.json()["state"]["fielding_substitutions"]["lineup"]
        self.assertTrue(any(p["pid"] == candidate["pid"] and p["slot"] == active["slot"]
                            for p in lineup))

        wrong = self.client.post("/api/live/pinch-hitter", json={"pid": fld["bench"][0]["pid"]})
        self.assertEqual(wrong.status_code, 409)

    def test_substitution_state_survives_save_and_load(self):
        user = self.data["meta"]["user_side"]
        data = self.step_until(lambda d: d["state"]["batting_side"] == user)
        pid = data["state"]["batting_substitutions"]["bench"][0]["pid"]
        changed = self.client.post("/api/live/pinch-hitter", json={"pid": pid}).json()
        expected = changed["state"]["batting_substitutions"]
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        self.client.post("/api/live/step")
        self.assertEqual(self.client.post("/api/game/load").status_code, 200)
        restored = self.client.get("/api/live/state").json()
        self.assertEqual(restored["state"]["batting_substitutions"], expected)


if __name__ == "__main__":
    unittest.main()
