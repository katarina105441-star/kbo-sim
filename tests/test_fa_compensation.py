"""FA 보상선수 엔진 검증."""
import pickle
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.development import ensure_farms
from kbo.league.fa import FASigning
from kbo.league.fa_compensation import InteractiveFACompensation


def prepared_case(grade="A", user_tid="KIA"):
    teams = load_league()
    ensure_farms(random.Random(77), teams, year=1)
    by_tid = {team.tid: team for team in teams}
    home, destination = by_tid["KIA"], by_tid["LG"]
    player = max(home.roster, key=lambda p: p.contract.salary)
    old_salary = max(1.0, player.contract.salary)
    multiplier = {"A": 3.0, "B": 2.0, "C": 1.5}[grade]
    comp = round(old_salary * multiplier, 2)
    home.roster.remove(player)
    destination.roster.append(player)
    player.team_id = destination.tid
    destination.budget = round(destination.budget - comp, 2)
    home.budget = round(home.budget + comp, 2)
    signing = FASigning(player, home.tid, destination.tid, grade,
                        old_salary * 1.2, old_salary, comp, 2,
                        (0.4, 0.3, 0.3))
    return teams, by_tid, signing, InteractiveFACompensation(
        teams, [signing], 1, user_tid)


class TestFACompensation(unittest.TestCase):
    def test_user_losing_team_can_select_unprotected_player(self):
        teams, by_tid, signing, session = prepared_case("A", "KIA")
        state = session.state()
        self.assertEqual(state["mode"], "select")
        self.assertEqual(state["signing"]["protection_count"], 20)
        self.assertTrue(state["candidates"])
        chosen = state["candidates"][0]
        home_before = by_tid["KIA"].budget
        destination_before = by_tid["LG"].budget

        result = session.choose_player(chosen["pid"])

        self.assertTrue(session.complete)
        self.assertEqual(result["kind"], "player")
        self.assertEqual(result["player"]["pid"], chosen["pid"])
        self.assertEqual(signing.compensation_kind, "player")
        self.assertLess(by_tid["KIA"].budget, home_before)
        self.assertGreater(by_tid["LG"].budget, destination_before)
        self.assertTrue(any(p.pid == chosen["pid"] for p in
                            by_tid["KIA"].roster + by_tid["KIA"].minors))

    def test_user_acquiring_team_must_submit_exact_protected_count(self):
        _teams, _by_tid, _signing, session = prepared_case("A", "LG")
        state = session.state()
        self.assertEqual(state["mode"], "protect")
        required = state["signing"]["protection_count"]
        with self.assertRaisesRegex(ValueError, "정확히"):
            session.submit_protection(state["recommended_protected"][:-1])
        result = session.submit_protection(state["recommended_protected"])
        self.assertIn(result["kind"], ("cash", "player"))
        self.assertTrue(session.complete)
        self.assertEqual(len(state["recommended_protected"]), required)

    def test_b_grade_uses_25_protected_and_lower_player_cash(self):
        _teams, _by_tid, signing, session = prepared_case("B", "KIA")
        state = session.state()
        self.assertEqual(state["signing"]["protection_count"], 25)
        self.assertAlmostEqual(state["signing"]["player_cash"], signing.comp / 2, places=2)

    def test_c_grade_is_cash_only_and_automatic(self):
        _teams, _by_tid, signing, session = prepared_case("C", "KIA")
        self.assertTrue(session.complete)
        self.assertEqual(session.results[0]["kind"], "cash")
        self.assertEqual(session.results[0]["cash"], signing.comp)

    def test_ai_only_case_completes_without_pause(self):
        _teams, _by_tid, _signing, session = prepared_case("A", "SSG")
        self.assertTrue(session.complete)
        self.assertEqual(len(session.results), 1)

    def test_pickle_preserves_pending_protection_state(self):
        _teams, _by_tid, _signing, session = prepared_case("A", "LG")
        restored = pickle.loads(pickle.dumps(session))
        self.assertEqual(restored.state(), session.state())
        self.assertEqual(restored.auto_protect()["kind"], session.auto_protect()["kind"])

    def test_cash_choice_keeps_full_cash(self):
        _teams, by_tid, signing, session = prepared_case("A", "KIA")
        before = by_tid["KIA"].budget
        result = session.choose_cash()
        self.assertEqual(result["kind"], "cash")
        self.assertEqual(result["cash"], signing.comp)
        self.assertEqual(by_tid["KIA"].budget, before)


if __name__ == "__main__":
    unittest.main()
