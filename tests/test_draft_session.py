"""중단 가능한 사용자 참여 드래프트 검증."""
import pickle
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.draft import run_draft
from kbo.league.draft_session import InteractiveDraft


def prepared_teams(holes=2):
    teams = load_league()
    for team in teams:
        team.roster = team.roster[:-holes]
    return teams


def fingerprint(results):
    return [
        (result.round, result.tid, result.player.pos,
         round(result.scouted, 8), round(result.true_val, 8))
        for result in results
    ]


class TestInteractiveDraft(unittest.TestCase):
    def test_all_auto_matches_existing_run_draft(self):
        teams1 = prepared_teams()
        rng1 = random.Random(20260710)
        expected = run_draft(rng1, teams1, list(teams1), year=1)

        teams2 = prepared_teams()
        rng2 = random.Random(20260710)
        draft = InteractiveDraft(rng2, teams2, list(teams2), 1, "KIA")
        draft.advance_to_user()
        while not draft.complete:
            self.assertTrue(draft.user_turn)
            draft.auto_pick()

        self.assertEqual(fingerprint(expected), fingerprint(draft.results))
        self.assertTrue(all(len(team.roster) == 25 for team in teams2))

    def test_manual_pick_selects_requested_prospect(self):
        teams = prepared_teams(holes=1)
        draft = InteractiveDraft(random.Random(77), teams, list(teams), 1, "KIA")
        draft.advance_to_user()
        state = draft.state()
        self.assertTrue(state["user_turn"])
        self.assertNotIn("true_val", state["candidates"][0])
        selected = state["candidates"][-1]

        result = draft.pick(selected["pid"])

        self.assertEqual(result.player.pid, selected["pid"])
        kia = next(team for team in teams if team.tid == "KIA")
        self.assertIn(result.player, kia.roster)

    def test_invalid_or_reused_prospect_is_rejected(self):
        teams = prepared_teams(holes=2)
        draft = InteractiveDraft(random.Random(88), teams, list(teams), 1, "KIA")
        draft.advance_to_user()
        pid = draft.state()["candidates"][0]["pid"]
        draft.pick(pid)
        with self.assertRaisesRegex(ValueError, "지명 가능한"):
            draft.pick(pid)

    def test_pickle_restores_cursor_pool_and_results(self):
        teams = prepared_teams(holes=2)
        draft = InteractiveDraft(random.Random(99), teams, list(teams), 1, "KIA")
        draft.advance_to_user()
        first = draft.state()["candidates"][0]["pid"]
        draft.pick(first)
        restored = pickle.loads(pickle.dumps(draft))

        self.assertEqual(restored.state(), draft.state())
        self.assertEqual(fingerprint(restored.results), fingerprint(draft.results))
        restored.auto_pick()
        self.assertGreaterEqual(len(restored.results), len(draft.results))

    def test_state_contains_scouting_and_need_but_not_true_ratings(self):
        teams = prepared_teams(holes=1)
        draft = InteractiveDraft(random.Random(123), teams, list(teams), 1, "KIA")
        draft.advance_to_user()
        state = draft.state()
        candidate = state["candidates"][0]
        self.assertIn(candidate["scout_grade"], "ABCDE")
        self.assertIn("scout_score", candidate)
        self.assertIn("need_bonus", candidate)
        self.assertIn("recommended", candidate)
        self.assertNotIn("ovr", candidate)
        self.assertNotIn("true_val", candidate)


if __name__ == "__main__":
    unittest.main()
