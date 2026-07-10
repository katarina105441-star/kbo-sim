"""감독 해임·재취업·구단 이동·미디어 반응 모델 검증."""
from types import SimpleNamespace
import unittest

from kbo.io.loader import load_league
from kbo.league.economy import init_market
from kbo.league.front_office import create_objective
from kbo.league.manager_career import (
    accept_job_offer,
    dismissal_reason,
    ensure_manager_career,
    generate_job_offers,
    manager_career_payload,
    process_season_career,
)
from kbo.league.team_identity import ensure_team_identities


class FakeSeason:
    def __init__(self, teams):
        self._teams = teams
        self.day = 144
        self.finished = True
        self.schedule = [None] * 144

    def standings(self):
        return list(self._teams)


class TestManagerCareer(unittest.TestCase):
    def make_session(self, tid="KIA", confidence=65.0):
        teams = load_league()
        init_market(teams)
        ensure_team_identities(teams)
        user_team = next(team for team in teams if team.tid == tid)
        user_team.user_managed = True
        session = SimpleNamespace(
            teams=teams,
            user_tid=tid,
            user_team=user_team,
            year=1,
            season=FakeSeason(teams),
            owner_confidence=confidence,
            front_office_history=[],
            current_objective=None,
            visible_records=lambda: None,
            offseason_standings=teams,
            trade_session=object(),
            fa_session=None,
            draft_session=None,
        )
        session.current_objective = create_objective(session)
        ensure_manager_career(session)
        return session

    @staticmethod
    def evaluation(year=1, grade="F", goal_met=False, champion=False,
                   target_rank=3, actual_rank=10):
        return {
            "year": year,
            "grade": grade,
            "goal_met": goal_met,
            "champion": champion,
            "target_rank": target_rank,
            "actual_rank": actual_rank,
        }

    def test_low_confidence_triggers_dismissal_reason(self):
        session = self.make_session(confidence=18)
        row = self.evaluation()
        session.front_office_history = [row]
        self.assertIn("신뢰도", dismissal_reason(session, row))

    def test_three_failures_trigger_dismissal_below_40(self):
        session = self.make_session(confidence=35)
        session.front_office_history = [
            self.evaluation(year=1), self.evaluation(year=2), self.evaluation(year=3)
        ]
        self.assertIn("3년 연속", dismissal_reason(session, session.front_office_history[-1]))

    def test_success_improves_reputation_and_fan_support(self):
        session = self.make_session(confidence=70)
        row = self.evaluation(grade="A", goal_met=True, target_rank=5, actual_rank=2)
        session.front_office_history = [row]
        process_season_career(session)
        self.assertEqual(session.career_status, "employed")
        self.assertEqual(session.manager_reputation, 57)
        self.assertEqual(session.fan_approval, 64)
        self.assertEqual(session.media_pressure, 17)
        self.assertFalse(row["dismissed"])

    def test_dismissal_creates_offers_and_clears_old_offseason(self):
        session = self.make_session(confidence=10)
        row = self.evaluation()
        session.front_office_history = [row]
        process_season_career(session)
        self.assertEqual(session.career_status, "dismissed")
        self.assertEqual(len(session.job_offers), 3)
        self.assertNotIn(session.user_tid, {offer["tid"] for offer in session.job_offers})
        self.assertIsNone(session.trade_session)
        self.assertFalse(session.user_team.user_managed)
        self.assertTrue(row["dismissed"])
        self.assertIsNotNone(session.manager_tenures[-1]["end_year"])

    def test_job_offers_are_deterministic(self):
        first = self.make_session(confidence=10)
        second = self.make_session(confidence=10)
        self.assertEqual(
            generate_job_offers(first, first.user_tid),
            generate_job_offers(second, second.user_tid),
        )

    def test_accept_offer_switches_team_and_records_move(self):
        session = self.make_session(confidence=10)
        session.front_office_history = [self.evaluation()]
        process_season_career(session)
        session.offseason_standings = None  # 순수 팀 전환만 검증
        offer = session.job_offers[0]
        old_team = session.user_team
        move = accept_job_offer(session, offer["tid"])
        self.assertEqual(session.career_status, "employed")
        self.assertEqual(session.user_tid, offer["tid"])
        self.assertFalse(old_team.user_managed)
        self.assertTrue(session.user_team.user_managed)
        self.assertEqual(move["to_tid"], offer["tid"])
        self.assertEqual(len(session.career_moves), 1)
        self.assertEqual(session.manager_tenures[-1]["tid"], offer["tid"])

    def test_invalid_offer_is_rejected(self):
        session = self.make_session(confidence=10)
        session.front_office_history = [self.evaluation()]
        process_season_career(session)
        with self.assertRaises(ValueError):
            accept_job_offer(session, "INVALID")

    def test_season_career_is_processed_only_once(self):
        session = self.make_session(confidence=70)
        session.front_office_history = [self.evaluation(grade="A", goal_met=True)]
        process_season_career(session)
        reputation = session.manager_reputation
        process_season_career(session)
        self.assertEqual(session.manager_reputation, reputation)
        self.assertEqual(len(session.media_feed), 1)

    def test_payload_contains_fan_media_and_tenure_history(self):
        session = self.make_session(confidence=70)
        payload = manager_career_payload(session)
        self.assertEqual(payload["status"], "employed")
        self.assertIn(payload["fan_label"], {"열광", "지지", "관망", "불만", "퇴진 요구"})
        self.assertIn(payload["media_label"], {"집중 포화", "고강도 압박", "비판적", "보통", "우호적"})
        self.assertEqual(len(payload["tenures"]), 1)

    def test_old_save_fields_are_migrated(self):
        session = self.make_session()
        for name in ("career_status", "manager_reputation", "fan_approval",
                     "media_pressure", "job_offers", "career_moves",
                     "media_feed", "career_processed_years", "manager_tenures"):
            delattr(session, name)
        ensure_manager_career(session)
        self.assertEqual(session.career_status, "employed")
        self.assertEqual(session.manager_reputation, 50.0)
        self.assertEqual(len(session.manager_tenures), 1)


if __name__ == "__main__":
    unittest.main()
