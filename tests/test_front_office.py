"""시즌 목표·구단주 신뢰도·해임 위험 모델 검증."""
from types import SimpleNamespace
import unittest

from kbo.io.loader import load_league
from kbo.league.front_office import (
    create_objective,
    dismissal_probability,
    ensure_front_office,
    evaluate_season,
    failed_streak,
    front_office_payload,
    risk_status,
)
from kbo.league.team_identity import ensure_team_identities


class FakeSeason:
    def __init__(self, teams):
        self._teams = teams

    def standings(self):
        return sorted(self._teams, key=lambda team: (team.pct, team.wins), reverse=True)


class TestFrontOffice(unittest.TestCase):
    def make_session(self, tid="KIA", year=1, confidence=65.0):
        teams = load_league()
        ensure_team_identities(teams)
        user_team = next(team for team in teams if team.tid == tid)
        return SimpleNamespace(
            teams=teams,
            user_tid=tid,
            user_team=user_team,
            year=year,
            owner_confidence=confidence,
            front_office_history=[],
            current_objective=None,
            season=FakeSeason(teams),
            visible_records=lambda: None,
        )

    def test_strategy_sets_different_rank_targets(self):
        contender = self.make_session("KIA")
        balanced = self.make_session("KT")
        rebuild = self.make_session("SAM")
        self.assertLess(create_objective(contender).target_rank,
                        create_objective(balanced).target_rank)
        self.assertLess(create_objective(balanced).target_rank,
                        create_objective(rebuild).target_rank)

    def test_high_confidence_raises_expectations(self):
        normal = self.make_session("KT", confidence=65)
        trusted = self.make_session("KT", confidence=90)
        self.assertLess(create_objective(trusted).target_rank,
                        create_objective(normal).target_rank)

    def test_previous_success_raises_next_goal(self):
        session = self.make_session("SAM", year=2)
        session.front_office_history.append({
            "actual_rank": 5, "target_rank": 7, "goal_met": True,
        })
        self.assertEqual(create_objective(session).target_rank, 6)

    def test_success_increases_confidence_and_records_grade(self):
        session = self.make_session("KT")
        ensure_front_office(session)
        target = session.current_objective.target_rank
        row = {"my_rank": max(1, target - 1), "my_record": "80승 4무 60패",
               "champion": "다른 팀"}
        result = evaluate_season(session, row)
        self.assertTrue(result["goal_met"])
        self.assertIn(result["grade"], {"A", "B"})
        self.assertGreater(session.owner_confidence, 65)
        self.assertEqual(session.front_office_history[-1], result)

    def test_failure_reduces_confidence(self):
        session = self.make_session("KIA")
        ensure_front_office(session)
        row = {"my_rank": 9, "my_record": "55승 5무 84패", "champion": "다른 팀"}
        result = evaluate_season(session, row)
        self.assertFalse(result["goal_met"])
        self.assertEqual(result["grade"], "F")
        self.assertLess(session.owner_confidence, 65)

    def test_championship_receives_s_grade_and_bonus(self):
        session = self.make_session("KIA")
        ensure_front_office(session)
        row = {"my_rank": 4, "my_record": "75승 5무 64패",
               "champion": session.user_team.name}
        result = evaluate_season(session, row)
        self.assertEqual(result["grade"], "S")
        self.assertTrue(result["champion"])
        self.assertGreater(result["confidence_delta"], 10)

    def test_failure_streak_increases_dismissal_risk(self):
        one_failure = [{"goal_met": False}]
        three_failures = [{"goal_met": False}] * 3
        self.assertEqual(failed_streak(three_failures), 3)
        self.assertGreater(dismissal_probability(30, three_failures),
                           dismissal_probability(30, one_failure))

    def test_success_breaks_failure_streak(self):
        history = [{"goal_met": False}, {"goal_met": True}, {"goal_met": False}]
        self.assertEqual(failed_streak(history), 1)

    def test_risk_status_thresholds(self):
        self.assertEqual(risk_status(82)[1], "secure")
        self.assertEqual(risk_status(40)[1], "pressure")
        self.assertEqual(risk_status(10)[1], "critical")

    def test_payload_contains_career_summary(self):
        session = self.make_session("KT")
        ensure_front_office(session)
        session.front_office_history = [
            {"year": 1, "actual_rank": 3, "target_rank": 5, "goal_met": True,
             "champion": False, "grade": "A", "confidence_after": 73},
            {"year": 2, "actual_rank": 6, "target_rank": 4, "goal_met": False,
             "champion": False, "grade": "D", "confidence_after": 60},
        ]
        payload = front_office_payload(session)
        self.assertEqual(payload["career"]["seasons"], 2)
        self.assertEqual(payload["career"]["goals_met"], 1)
        self.assertEqual(payload["career"]["best_rank"], 3)
        self.assertEqual(len(payload["history"]), 2)


if __name__ == "__main__":
    unittest.main()
