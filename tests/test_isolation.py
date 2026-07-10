"""웹 전용 RNG 격리 모드 검증.

공유 모드는 기존 test_watch 앵커가 가드한다. 이 파일은 격리 모드의 자체
재현성과 경기/팀 스트림 간 난수 소비 독립성을 최소 4개 시즌 시드로 검증한다.
"""
import random
import unittest
from unittest.mock import patch

from kbo.engine.game import GameSimulator
from kbo.io.loader import load_league
from kbo.league.season import SeasonRunner, _stable_seed

SEEDS = (7, 42, 2026, 90210)
USER_TID = "KIA"


def fingerprint(teams, season):
    rows = [(t.tid, t.wins, t.ties, t.losses) for t in season.standings()]
    players = []
    for team in teams:
        for p in sorted(team.roster, key=lambda item: item.pid):
            players.append((p.pid, p.season_bat.pa, p.season_bat.h,
                            p.season_bat.hr, p.season_pit.outs,
                            p.season_pit.er, p.inj_days, p.missed,
                            round(p.form_season, 12), round(p.form_day, 12)))
    return rows, players


def run_isolated(seed):
    teams = load_league()
    season = SeasonRunner(teams, random.Random(seed), isolated=True)
    season.run()
    return fingerprint(teams, season)


def run_days(seed, extra_user_draws=False, days=8):
    teams = load_league()
    season = SeasonRunner(teams, random.Random(seed), isolated=True)
    season.start()
    original = GameSimulator.run

    def run_with_extra_draws(sim):
        result = original(sim)
        if extra_user_draws and USER_TID in (sim.home.tid, sim.away.tid):
            # 결과가 확정된 뒤에도 공유 스트림이라면 다음 경기 RNG가 이동한다.
            # 격리 모드에서는 이 경기 전용 Random만 소비하므로 밖으로 새지 않는다.
            for _ in range(500):
                sim.rng.random()
        return result

    daily = []
    with patch.object(GameSimulator, "run", run_with_extra_draws):
        for _ in range(days):
            results = season.step_day()
            daily.append({
                tuple(sorted((r.home.tid, r.away.tid))):
                (r.score, r.tie, r.innings)
                for r in results
            })
    team_state = {
        team.tid: tuple((p.pid, p.inj_days, p.missed,
                         round(p.form_day, 12))
                        for p in sorted(team.roster, key=lambda item: item.pid))
        for team in teams
    }
    return daily, team_state


class TestIsolatedRng(unittest.TestCase):
    def test_stable_seed_anchor(self):
        """내장 hash salt와 무관한 blake2b 시드 형식을 고정한다."""
        self.assertEqual(_stable_seed(123, "day", 7),
                         145119920055293442799790861243193919294)

    def test_reproducible_full_season_four_seeds(self):
        for seed in SEEDS:
            self.assertEqual(run_isolated(seed), run_isolated(seed),
                             f"isolated seed {seed} 재현 실패")

    def test_extra_user_game_draws_do_not_change_other_games(self):
        for seed in SEEDS:
            base, _ = run_days(seed, False, days=1)
            extra, _ = run_days(seed, True, days=1)
            other_games = [key for key in base[0] if USER_TID not in key]
            self.assertEqual(len(other_games), 4)
            for key in other_games:
                self.assertEqual(base[0][key], extra[0][key],
                                 f"seed {seed}, game {key}")

    def test_extra_user_game_draws_do_not_change_team_ticks(self):
        for seed in SEEDS:
            _, base = run_days(seed, False)
            _, extra = run_days(seed, True)
            self.assertEqual(base, extra, f"seed {seed}: 부상/폼 스트림 이동")

    def test_default_mode_is_shared(self):
        season = SeasonRunner(load_league(), random.Random(1))
        self.assertFalse(season.isolated)
        self.assertIsNone(season._isolation_root)


if __name__ == "__main__":
    unittest.main()
