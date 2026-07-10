"""2군·육성 엔진 검증."""
import pickle
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.development import (
    ACTIVE_MAX,
    accrue_minor_days,
    auto_assign_active,
    auto_cover_injuries,
    demote,
    development_tick,
    ensure_farms,
    promote,
    set_focus,
)


class TestDevelopmentEngine(unittest.TestCase):
    def setUp(self):
        self.teams = load_league()
        ensure_farms(random.Random(100), self.teams, year=1)
        self.team = self.teams[0]

    def test_initial_farm_has_five_unique_players(self):
        for team in self.teams:
            self.assertEqual(len(team.minors), 5)
            ids = [p.pid for p in team.roster + team.minors]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(all(p.team_id == team.tid for p in team.minors))

    def test_promote_and_demote_move_single_player(self):
        prospect = self.team.minors[0]
        before = len(self.team.roster)
        promote(self.team, prospect.pid)
        self.assertEqual(len(self.team.roster), before + 1)
        self.assertIn(prospect, self.team.roster)
        self.assertNotIn(prospect, self.team.minors)

        demote(self.team, prospect.pid)
        self.assertEqual(len(self.team.roster), before)
        self.assertIn(prospect, self.team.minors)

    def test_active_roster_max_is_enforced(self):
        while self.team.minors and len(self.team.roster) < ACTIVE_MAX:
            promote(self.team, self.team.minors[0].pid)
        self.assertEqual(len(self.team.roster), ACTIVE_MAX)
        if self.team.minors:
            with self.assertRaisesRegex(ValueError, "최대"):
                promote(self.team, self.team.minors[0].pid)

    def test_focus_validation_by_player_type(self):
        batter = next(p for p in self.team.minors if not p.is_pitcher)
        pitcher = next(p for p in self.team.minors if p.is_pitcher)
        self.assertEqual(set_focus(self.team, batter.pid, "power").development_focus,
                         "power")
        self.assertEqual(set_focus(self.team, pitcher.pid, "control").development_focus,
                         "control")
        with self.assertRaisesRegex(ValueError, "투수"):
            set_focus(self.team, pitcher.pid, "power")
        with self.assertRaisesRegex(ValueError, "야수"):
            set_focus(self.team, batter.pid, "velocity")

    def test_minor_days_produce_growth_and_age_one_year(self):
        player = self.team.minors[0]
        player.age = 20
        player.minor_days = 144
        player.tal_g = 1.3
        before_age = player.age
        before_ovr = player.pit_overall if player.is_pitcher else player.bat_overall

        report = development_tick(random.Random(5), self.teams)

        after_ovr = player.pit_overall if player.is_pitcher else player.bat_overall
        self.assertEqual(player.age, before_age + 1)
        self.assertGreater(after_ovr, before_ovr)
        self.assertGreater(player.dev_last_gain, 0)
        self.assertEqual(player.minor_days, 0)
        self.assertEqual(player.minor_seasons, 1)
        self.assertTrue(any(row[1] is player for row in report.gains))

    def test_accrue_minor_days(self):
        accrue_minor_days(self.teams, 7)
        self.assertTrue(all(p.minor_days == 7
                            for team in self.teams for p in team.minors))

    def test_injury_shortage_calls_up_best_healthy_minor(self):
        active_batters = [p for p in self.team.roster if not p.is_pitcher]
        for player in active_batters[:6]:
            player.inj_days = 20
        healthy_before = sum(not p.is_pitcher and p.inj_days == 0
                             for p in self.team.roster)
        self.assertLess(healthy_before, 9)

        moves = auto_cover_injuries(self.team)

        self.assertTrue(moves)
        healthy_after = sum(not p.is_pitcher and p.inj_days == 0
                            for p in self.team.roster)
        self.assertGreaterEqual(healthy_after, 9)

    def test_auto_assign_returns_to_25_active_players(self):
        promote(self.team, self.team.minors[0].pid)
        result = auto_assign_active(self.team)
        self.assertEqual(len(self.team.roster), 25)
        self.assertEqual(len(self.team.roster) + len(self.team.minors), 30)
        self.assertIn("promoted", result)
        self.assertIn("demoted", result)

    def test_pickle_preserves_farm_and_focus(self):
        player = self.team.minors[0]
        player.development_focus = "balanced"
        player.minor_days = 44
        restored = pickle.loads(pickle.dumps(self.team))
        self.assertEqual(len(restored.minors), 5)
        restored_player = next(p for p in restored.minors if p.pid == player.pid)
        self.assertEqual(restored_player.minor_days, 44)
        self.assertEqual(restored_player.development_focus, "balanced")


if __name__ == "__main__":
    unittest.main()
