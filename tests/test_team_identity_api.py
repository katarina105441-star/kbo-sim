"""구단 성향 API와 웹 AI 패치 통합 검증."""
import os
import random
import unittest

from fastapi.testclient import TestClient

import web.backend.main as main
from kbo.io.loader import load_league
from kbo.league.draft_session import InteractiveDraft
from kbo.league.team_identity import ensure_team_identities
from web.backend.session import SAVE_DIR


class TestTeamIdentityApi(unittest.TestCase):
    def setUp(self):
        main.SESSION = None
        self.client = TestClient(main.app)

    def tearDown(self):
        path = os.path.join(SAVE_DIR, "save.pkl")
        if os.path.exists(path):
            os.remove(path)

    def test_identity_endpoint_lists_all_teams(self):
        response = self.client.get("/api/teams/identities")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 10)
        self.assertEqual(body["KIA"]["strategy_label"], "윈나우")
        self.assertIn("scouting", body["KT"])

    def test_new_game_state_exposes_user_identity(self):
        response = self.client.post(
            "/api/game/new", json={"tid": "HWE", "seed": 20260711})
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()["my_team"]["identity"]
        self.assertEqual(identity["key"], "high-variance-rebuild")
        self.assertEqual(identity["strategy"], "rebuild")

    def test_interactive_draft_has_team_specific_scouting_boards(self):
        teams = load_league()
        ensure_team_identities(teams)
        draft = InteractiveDraft(random.Random(991), teams, list(teams), 1, "KIA")
        self.assertEqual(set(draft.team_boards), {team.tid for team in teams})
        player = draft.pool[0]
        true_values = {round(board[player.pid][1], 8)
                       for board in draft.team_boards.values()}
        observed = {round(board[player.pid][0], 8)
                    for board in draft.team_boards.values()}
        self.assertEqual(len(true_values), 1)
        self.assertGreater(len(observed), 1)

    def test_game_save_load_preserves_identity(self):
        self.client.post("/api/game/new", json={"tid": "KT", "seed": 123})
        before = self.client.get("/api/game/state").json()["my_team"]["identity"]
        self.assertEqual(self.client.post("/api/game/save").status_code, 200)
        main.SESSION.user_team.identity = None
        loaded = self.client.post("/api/game/load")
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json()["my_team"]["identity"], before)


if __name__ == "__main__":
    unittest.main()
