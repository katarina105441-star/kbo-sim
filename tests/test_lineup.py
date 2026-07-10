"""MVP-3 Part 1 라인업 API·검증·자동 대체 테스트."""
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main


class TestLineupApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)
        response = self.client.post("/api/game/new", json={"tid": "KIA", "seed": 42})
        self.assertEqual(response.status_code, 200)

    def current(self):
        response = self.client.get("/api/my/lineup")
        self.assertEqual(response.status_code, 200)
        return response.json()

    @staticmethod
    def body(data):
        return {
            "order": list(data["order"]),
            "slots": dict(data["slots"]),
            "rotation": list(data["rotation"]),
            "closer": data["closer"],
            "setup": list(data["setup"]),
        }

    def test_get_shape_and_web_uses_isolation(self):
        data = self.current()
        self.assertEqual(len(data["order"]), 9)
        self.assertEqual(set(data["slots"]),
                         {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"})
        self.assertEqual(len(data["rotation"]), 5)
        self.assertTrue(main.SESSION.season.isolated)

    def test_duplicate_order_rejected_atomically(self):
        before = self.current()
        body = self.body(before)
        body["order"][1] = body["order"][0]
        response = self.client.put("/api/my/lineup", json=body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.current()["order"], before["order"])

    def test_pitcher_and_injured_player_rejected(self):
        data = self.current()
        body = self.body(data)
        pitcher = data["pitchers"][0]["pid"]
        replaced = body["order"][0]
        body["order"][0] = pitcher
        slot = next(s for s, pid in body["slots"].items() if pid == replaced)
        body["slots"][slot] = pitcher
        self.assertEqual(self.client.put("/api/my/lineup", json=body).status_code, 422)

        data = self.current()
        hurt_pid = data["order"][0]
        next(p for p in main.SESSION.user_team.roster if p.pid == hurt_pid).inj_days = 3
        self.assertEqual(self.client.put("/api/my/lineup",
                                         json=self.body(data)).status_code, 422)

    def test_slots_must_be_complete_unique_and_match_order(self):
        data = self.current()
        missing = self.body(data)
        missing["slots"].pop("DH")
        self.assertEqual(self.client.put("/api/my/lineup", json=missing).status_code, 422)

        data = self.current()
        duplicate = self.body(data)
        duplicate["slots"]["DH"] = duplicate["slots"]["C"]
        self.assertEqual(self.client.put("/api/my/lineup", json=duplicate).status_code, 422)

    def test_pitcher_roles_are_disjoint(self):
        data = self.current()
        duplicate_rotation = self.body(data)
        duplicate_rotation["rotation"][1] = duplicate_rotation["rotation"][0]
        self.assertEqual(self.client.put("/api/my/lineup",
                                         json=duplicate_rotation).status_code, 422)

        data = self.current()
        overlap = self.body(data)
        overlap["setup"] = [overlap["closer"]]
        response = self.client.put("/api/my/lineup", json=overlap)
        self.assertEqual(response.status_code, 422)
        self.assertIn("서로 겹칠 수 없습니다", response.json()["detail"])

    def test_saving_lineup_preserves_next_starter(self):
        data = self.current()
        team = main.SESSION.user_team
        team.rot_idx = 3
        next_starter_pid = team.rotation[team.rot_idx % len(team.rotation)].pid

        response = self.client.put("/api/my/lineup", json=self.body(data))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            team.rotation[team.rot_idx % len(team.rotation)].pid,
            next_starter_pid,
        )

    def test_position_mismatch_is_saved_with_warning(self):
        data = self.current()
        body = self.body(data)
        body["slots"]["C"], body["slots"]["SS"] = (
            body["slots"]["SS"], body["slots"]["C"])
        response = self.client.put("/api/my/lineup", json=body)
        self.assertEqual(response.status_code, 200)
        warnings = response.json()["warnings"]
        self.assertTrue(any(w["slot"] in ("C", "SS") for w in warnings))

    def test_injury_auto_replacement_preserves_order_and_slots(self):
        data = self.current()
        team = main.SESSION.user_team
        old_lineup = [(p.pid, slot) for p, slot in team.lineup]
        hurt = team.lineup[0][0]
        hurt.inj_days = 5
        team.refresh_lineup()
        new_lineup = [(p.pid, slot) for p, slot in team.lineup]
        self.assertNotEqual(new_lineup[0][0], hurt.pid)
        self.assertEqual([slot for _, slot in new_lineup],
                         [slot for _, slot in old_lineup])
        self.assertEqual(new_lineup[1:], old_lineup[1:])
        replacement = team.lineup[0][0]
        self.assertEqual(replacement.inj_days, 0)

    def test_ai_recommend_restores_valid_configuration(self):
        data = self.current()
        body = self.body(data)
        body["order"] = list(reversed(body["order"]))
        saved = self.client.put("/api/my/lineup", json=body)
        self.assertEqual(saved.status_code, 200)
        recommended = self.client.put("/api/my/lineup", json={"use_ai": True})
        self.assertEqual(recommended.status_code, 200)
        result = recommended.json()
        self.assertEqual(len(result["order"]), 9)
        self.assertEqual(len(result["rotation"]), 5)
        roles = result["rotation"] + [result["closer"]] + result["setup"]
        self.assertEqual(len(roles), len(set(roles)))

        # 시즌 중 부상자가 생겨도 AI 추천은 건강한 스윙맨으로 보직을 재구성한다.
        hurt_pid = result["rotation"][0]
        next(p for p in main.SESSION.user_team.roster if p.pid == hurt_pid).inj_days = 7
        healthy = self.client.put("/api/my/lineup", json={"use_ai": True})
        self.assertEqual(healthy.status_code, 200)
        healthy_roles = (healthy.json()["rotation"] + [healthy.json()["closer"]]
                         + healthy.json()["setup"])
        self.assertNotIn(hurt_pid, healthy_roles)


if __name__ == "__main__":
    unittest.main()
