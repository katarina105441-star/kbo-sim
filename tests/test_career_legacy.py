"""감독 은퇴·명예의 전당·커리어 결산 모델 검증."""
from types import SimpleNamespace
import unittest

from kbo.io.loader import load_league
from kbo.league.career_legacy import (
    MANDATORY_RETIREMENT_SEASONS,
    VOLUNTARY_RETIREMENT_SEASONS,
    balance_assessment,
    career_legacy_payload,
    career_totals,
    ensure_career_legacy,
    legacy_score,
    legacy_tier,
    maybe_auto_retire,
    retire_manager,
    retirement_eligible,
)
from kbo.league.economy import init_market
from kbo.league.front_office import create_objective
from kbo.league.team_identity import ensure_team_identities


class FakeSeason:
    def __init__(self, teams):
        self._teams = teams
        self.day = 0
        self.finished = False
        self.schedule = [None] * 144

    def standings(self):
        return list(self._teams)


class TestCareerLegacy(unittest.TestCase):
    def make_session(self, seasons=0, championships=0, dismissals=0):
        teams = load_league()
        init_market(teams)
        ensure_team_identities(teams)
        user_team = teams[0]
        user_team.user_managed = True
        history = []
        for year in range(1, seasons + 1):
            champion = year <= championships
            dismissed = year <= dismissals
            rank = 1 if champion else 4 + (year % 4)
            history.append({
                "year": year,
                "actual_rank": rank,
                "target_rank": 5,
                "record": f"{70 + year % 10}승 {year % 4}무 {60 + year % 9}패",
                "champion": champion,
                "goal_met": champion or rank <= 5,
                "grade": "S" if champion else ("B" if rank <= 5 else "D"),
                "dismissed": dismissed,
            })
        session = SimpleNamespace(
            teams=teams,
            user_tid=user_team.tid,
            user_team=user_team,
            year=max(1, seasons),
            season=FakeSeason(teams),
            visible_records=lambda: None,
            owner_confidence=65.0,
            front_office_history=history,
            current_objective=None,
            career_status="employed",
            manager_reputation=72.0,
            fan_approval=60.0,
            media_pressure=25.0,
            job_offers=[],
            career_moves=[],
            media_feed=[],
            career_processed_years=set(),
            manager_tenures=[{
                "tid": user_team.tid, "team": user_team.name,
                "start_year": 1, "end_year": None, "exit_reason": None,
            }],
            trade_session=object(),
            fa_session=object(),
            draft_session=object(),
        )
        session.current_objective = create_objective(session)
        ensure_career_legacy(session)
        return session

    def test_record_and_career_totals(self):
        session = self.make_session(seasons=3, championships=1)
        totals = career_totals(session)
        self.assertEqual(totals["seasons"], 3)
        self.assertEqual(totals["championships"], 1)
        self.assertGreater(totals["record"]["wins"], 200)
        self.assertEqual(totals["team_count"], 1)
        self.assertGreater(totals["games"], 0)

    def test_retirement_requires_ten_completed_seasons(self):
        nine = self.make_session(seasons=VOLUNTARY_RETIREMENT_SEASONS - 1)
        ten = self.make_session(seasons=VOLUNTARY_RETIREMENT_SEASONS)
        self.assertFalse(retirement_eligible(nine))
        self.assertTrue(retirement_eligible(ten))
        with self.assertRaises(ValueError):
            retire_manager(nine)

    def test_voluntary_retirement_closes_career(self):
        session = self.make_session(seasons=12, championships=2)
        summary = retire_manager(session)
        self.assertEqual(session.career_status, "retired")
        self.assertEqual(summary["reason"], "voluntary")
        self.assertEqual(summary["totals"]["seasons"], 12)
        self.assertIsNone(session.trade_session)
        self.assertIsNone(session.fa_session)
        self.assertIsNone(session.draft_session)
        self.assertFalse(any(team.user_managed for team in session.teams))
        self.assertIsNotNone(session.manager_tenures[-1]["end_year"])
        self.assertIsNotNone(session.hall_of_fame)

    def test_retirement_cannot_be_repeated(self):
        session = self.make_session(seasons=10)
        retire_manager(session)
        with self.assertRaises(LookupError):
            retire_manager(session)

    def test_thirty_seasons_trigger_automatic_retirement(self):
        session = self.make_session(seasons=MANDATORY_RETIREMENT_SEASONS)
        summary = maybe_auto_retire(session)
        self.assertIsNotNone(summary)
        self.assertEqual(session.career_status, "retired")
        self.assertEqual(summary["reason"], "mandatory")

    def test_twenty_nine_seasons_do_not_auto_retire(self):
        session = self.make_session(seasons=MANDATORY_RETIREMENT_SEASONS - 1)
        self.assertIsNone(maybe_auto_retire(session))
        self.assertEqual(session.career_status, "employed")

    def test_championships_raise_legacy_score(self):
        ordinary = self.make_session(seasons=15, championships=0)
        champion = self.make_session(seasons=15, championships=3)
        self.assertGreater(legacy_score(champion), legacy_score(ordinary))

    def test_dismissals_reduce_legacy_score(self):
        stable = self.make_session(seasons=15, championships=1, dismissals=0)
        fired = self.make_session(seasons=15, championships=1, dismissals=3)
        self.assertLess(legacy_score(fired), legacy_score(stable))

    def test_legacy_tiers_are_ordered(self):
        self.assertEqual(legacy_tier(140)["key"], "legend")
        self.assertEqual(legacy_tier(100)["key"], "hall_of_fame")
        self.assertEqual(legacy_tier(70)["key"], "master")
        self.assertEqual(legacy_tier(45)["key"], "veteran")
        self.assertEqual(legacy_tier(10)["key"], "career")

    def test_payload_contains_preview_and_final_summary(self):
        session = self.make_session(seasons=10, championships=1)
        before = career_legacy_payload(session)
        self.assertTrue(before["retirement_eligible"])
        self.assertIsNone(before["retirement_summary"])
        retire_manager(session)
        after = career_legacy_payload(session)
        self.assertIsNotNone(after["retirement_summary"])
        self.assertEqual(after["legacy_preview"]["totals"]["seasons"], 10)

    def test_old_save_fields_are_migrated(self):
        session = self.make_session(seasons=2)
        for name in ("retirement_summary", "hall_of_fame",
                     "retirement_year", "retirement_reason"):
            delattr(session, name)
        ensure_career_legacy(session)
        self.assertIsNone(session.retirement_summary)
        self.assertIsNone(session.hall_of_fame)

    def test_balance_assessment_passes_reasonable_distribution(self):
        careers = [
            {"dismissals": 1, "championships": 2, "team_count": 2, "inducted": True},
            {"dismissals": 2, "championships": 1, "team_count": 3, "inducted": False},
            {"dismissals": 3, "championships": 0, "team_count": 3, "inducted": False},
            {"dismissals": 1, "championships": 3, "team_count": 2, "inducted": True},
        ]
        report = balance_assessment(careers)
        self.assertTrue(report["passed"])
        self.assertEqual(report["sample_size"], 4)

    def test_balance_assessment_detects_extreme_hall_rate(self):
        careers = [
            {"dismissals": 1, "championships": 2, "team_count": 2, "inducted": True}
            for _ in range(10)
        ]
        report = balance_assessment(careers)
        self.assertFalse(report["passed"])
        failed = {row["name"] for row in report["checks"] if not row["passed"]}
        self.assertIn("명예의 전당 비율", failed)


if __name__ == "__main__":
    unittest.main()
