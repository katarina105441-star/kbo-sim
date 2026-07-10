"""구단주 이벤트·시즌 보상·업적 엔진 검증."""
from types import SimpleNamespace
import unittest

from kbo.io.loader import load_league
from kbo.league.engagement import (
    EVENT_MILESTONES,
    apply_season_rewards,
    engagement_payload,
    ensure_engagement,
    maybe_issue_event,
    resolve_owner_event,
    unlock_achievements,
)
from kbo.league.front_office import create_objective
from kbo.league.team_identity import ensure_team_identities


class FakeSeason:
    def __init__(self, teams, day=0):
        self._teams = teams
        self.day = day
        self.finished = False
        self.schedule = [None] * 144

    def standings(self):
        return list(self._teams)


class TestEngagement(unittest.TestCase):
    def make_session(self, tid="KIA", day=0):
        teams = load_league()
        ensure_team_identities(teams)
        user_team = next(team for team in teams if team.tid == tid)
        session = SimpleNamespace(
            teams=teams,
            user_tid=tid,
            user_team=user_team,
            year=1,
            season=FakeSeason(teams, day),
            owner_confidence=65.0,
            front_office_history=[],
            current_objective=None,
            visible_records=lambda: None,
        )
        session.current_objective = create_objective(session)
        ensure_engagement(session)
        return session

    def test_event_is_issued_at_first_milestone(self):
        session = self.make_session(day=EVENT_MILESTONES[0])
        event = maybe_issue_event(session)
        self.assertIsNotNone(event)
        self.assertEqual(event["milestone"], 24)
        self.assertEqual(len(event["choices"]), 2)

    def test_event_is_not_duplicated(self):
        session = self.make_session(day=24)
        first = maybe_issue_event(session)
        second = maybe_issue_event(session)
        self.assertEqual(first["id"], second["id"])
        resolve_owner_event(session, first["choices"][0]["id"])
        self.assertIsNone(maybe_issue_event(session))

    def test_large_jump_only_issues_latest_due_event(self):
        session = self.make_session(day=100)
        event = maybe_issue_event(session)
        self.assertEqual(event["milestone"], 72)
        self.assertIn("1:24", session.issued_owner_events)
        self.assertIn("1:72", session.issued_owner_events)

    def test_choice_applies_effects_and_unlocks_first_event(self):
        session = self.make_session(day=24)
        event = maybe_issue_event(session)
        choice = event["choices"][0]
        before_budget = session.user_team.budget
        before_confidence = session.owner_confidence
        result = resolve_owner_event(session, choice["id"])
        self.assertEqual(
            session.user_team.budget,
            round(before_budget + choice["effects"]["budget"] + 2.0, 2),
        )
        self.assertEqual(session.owner_confidence,
                         before_confidence + choice["effects"]["confidence"])
        self.assertEqual(session.front_office_points, choice["effects"]["points"])
        self.assertIn("boardroom_debut", session.achievements)
        self.assertTrue(result["unlocked"])

    def test_invalid_choice_is_rejected(self):
        session = self.make_session(day=24)
        maybe_issue_event(session)
        with self.assertRaises(ValueError):
            resolve_owner_event(session, "unknown")

    def test_goal_reward_is_paid_once(self):
        session = self.make_session()
        session.front_office_history.append({
            "year": 1, "target_rank": 5, "actual_rank": 3,
            "goal_met": True, "champion": False,
        })
        before = session.user_team.budget
        first = apply_season_rewards(session)
        after = session.user_team.budget
        second = apply_season_rewards(session)
        self.assertEqual(first["reward_budget"], 9.0)
        self.assertEqual(after, before + 9.0 + 4.0)  # 목표 업적 예산 포함
        self.assertEqual(session.user_team.budget, after)
        self.assertEqual(second["reward_budget"], 9.0)
        self.assertIn("first_objective", session.achievements)

    def test_championship_unlocks_champion_achievement(self):
        session = self.make_session()
        session.front_office_history.append({
            "year": 1, "target_rank": 3, "actual_rank": 4,
            "goal_met": True, "champion": True,
        })
        apply_season_rewards(session)
        self.assertIn("champion", session.achievements)
        self.assertEqual(session.front_office_points, 5)

    def test_turnaround_achievement(self):
        session = self.make_session()
        session.front_office_history = [
            {"year": 1, "goal_met": False, "champion": False,
             "target_rank": 5, "actual_rank": 8},
            {"year": 2, "goal_met": True, "champion": False,
             "target_rank": 6, "actual_rank": 4},
        ]
        unlocked = unlock_achievements(session)
        self.assertIn("turnaround", {row["id"] for row in unlocked})

    def test_payload_lists_locked_and_unlocked_achievements(self):
        session = self.make_session(day=24)
        maybe_issue_event(session)
        resolve_owner_event(session, "results")
        payload = engagement_payload(session)
        self.assertEqual(payload["achievement_total"], 8)
        self.assertEqual(payload["achievement_count"], 1)
        self.assertTrue(any(row["id"] == "boardroom_debut" and row["unlocked"]
                            for row in payload["achievements"]))

    def test_old_save_fields_are_migrated(self):
        session = self.make_session()
        for name in ("pending_owner_event", "issued_owner_events",
                     "owner_event_history", "front_office_points",
                     "achievements", "rewarded_seasons"):
            delattr(session, name)
        ensure_engagement(session)
        self.assertIsNone(session.pending_owner_event)
        self.assertEqual(session.front_office_points, 0)
        self.assertEqual(session.achievements, {})


if __name__ == "__main__":
    unittest.main()
