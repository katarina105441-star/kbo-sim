"""실시간 사용자 경기를 위한 SeasonRunner 날짜 분할 검증."""
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.season import SeasonRunner

USER_TID = "KIA"


def game_fp(res):
    return (res.home.tid, res.away.tid, res.score, res.tie, res.innings,
            tuple((side, tuple((st.player.pid, st.line.outs, st.line.pitches,
                                st.line.r, st.line.er)
                               for st in res.stints[side]))
                  for side in ("home", "away")))


def team_tick_fp(teams, excluded=()):
    return {
        t.tid: tuple((p.pid, p.inj_days, p.missed,
                      round(p.form_day, 12))
                     for p in sorted(t.roster, key=lambda x: x.pid))
        for t in teams if t.tid not in excluded
    }


class TestLiveSeasonDay(unittest.TestCase):
    def make(self, seed=42):
        teams = load_league()
        season = SeasonRunner(teams, random.Random(seed), isolated=True)
        season.start()
        return teams, season

    def test_managed_day_waits_for_game_completion(self):
        _teams, season = self.make()
        ctx = season.begin_day(USER_TID)
        self.assertEqual(season.day, 0)
        self.assertIs(season.pending_day, ctx)
        self.assertEqual(sum(r is not None for r in ctx.results), 4)
        self.assertFalse(ctx.managed_sim.done)
        with self.assertRaisesRegex(RuntimeError, "아직 종료"):
            season.complete_day()

        ctx.managed_sim.finish_auto()
        results = season.complete_managed_game()
        self.assertEqual(len(results), 5)
        self.assertEqual(season.day, 1)
        self.assertIsNone(season.pending_day)
        with self.assertRaisesRegex(RuntimeError, "진행 중인 날짜"):
            season.complete_day()

    def test_split_auto_game_matches_normal_step_day(self):
        teams1, normal = self.make(2026)
        expected = normal.step_day()

        teams2, managed = self.make(2026)
        ctx = managed.begin_day(USER_TID)
        ctx.managed_sim.finish_auto()
        actual = managed.complete_managed_game()

        self.assertEqual([game_fp(r) for r in expected],
                         [game_fp(r) for r in actual])
        self.assertEqual(team_tick_fp(teams1), team_tick_fp(teams2))

    def test_manual_change_does_not_change_other_games_or_other_team_ticks(self):
        teams1, base = self.make(90210)
        ctx1 = base.begin_day(USER_TID)
        managed_game1 = ctx1.managed_sim
        participant_tids = {managed_game1.home.tid, managed_game1.away.tid}
        managed_idx = ctx1.managed_idx
        managed_game1.finish_auto()
        result1 = base.complete_managed_game()

        teams2, changed = self.make(90210)
        ctx2 = changed.begin_day(USER_TID)
        sim2 = ctx2.managed_sim
        user_side = "home" if sim2.home.tid == USER_TID else "away"
        # 사용자가 공격 중이면 첫 타석들을 진행해 수비 시점까지 이동한다.
        guard = 0
        while sim2.state()["fielding_side"] != user_side:
            sim2.step_pa()
            guard += 1
            self.assertLess(guard, 50)
        reliever = sim2.state()["available_relievers"][0]["pid"]
        sim2.force_pitcher_change(user_side, reliever)
        sim2.finish_auto()
        result2 = changed.complete_managed_game()

        other1 = [game_fp(r) for i, r in enumerate(result1) if i != managed_idx]
        other2 = [game_fp(r) for i, r in enumerate(result2) if i != ctx2.managed_idx]
        self.assertEqual(other1, other2)
        self.assertEqual(team_tick_fp(teams1, participant_tids),
                         team_tick_fp(teams2, participant_tids))

    def test_duplicate_begin_is_rejected(self):
        _teams, season = self.make()
        season.begin_day(USER_TID)
        with self.assertRaisesRegex(RuntimeError, "진행 중인 날짜"):
            season.begin_day(USER_TID)


if __name__ == "__main__":
    unittest.main()
