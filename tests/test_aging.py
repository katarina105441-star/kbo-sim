"""에이징 커브 검증 — 곡선 모양 / 클램프 / 시드 재현 / 은퇴·1:1 대체 / 시즌 중 무변화."""
import random
import unittest

from kbo.engine.game import GameSimulator
from kbo.engine.probability import TUNE
from kbo.io.loader import load_league
from kbo.league.aging import (base_delta, expected_delta, offseason_tick,
                              overall, potential)


def snapshot(teams):
    out = {}
    for t in teams:
        for p in t.roster:
            r = p.pit if p.is_pitcher else p.bat
            out[p.pid] = {k: v for k, v in vars(r).items()}
    return out


class TestCurveShape(unittest.TestCase):
    def test_four_segments(self):
        curve = TUNE["aging"]["bat_curve"]["contact"]  # (2.2, 26, 30, 0.6, 35, 2.2)
        self.assertGreater(base_delta(curve, 21), 0)          # 성장기
        self.assertEqual(base_delta(curve, 28), 0.0)          # 피크
        self.assertLess(base_delta(curve, 32), 0)             # 완만 하락
        self.assertLess(base_delta(curve, 38), base_delta(curve, 32))  # 급락

    def test_catcher_declines_earlier(self):
        """포수는 하락 시작 1년 앞당김: 피크끝 나이에서 이미 하락."""
        curve = TUNE["aging"]["bat_curve"]["contact"]
        peak_end = curve[2]
        self.assertEqual(base_delta(curve, peak_end), 0.0)
        self.assertLess(base_delta(curve, peak_end, decline_shift=1), 0)

    def test_talent_scales_growth_and_decline(self):
        teams = load_league()
        p = next(x for t in teams for x in t.roster if not x.is_pitcher)
        p.tal_g, p.tal_d = 1.5, 1.5
        self.assertGreater(expected_delta(p, "contact", 21), 2.2)   # 성장 ×g
        self.assertGreater(expected_delta(p, "contact", 38), -2.2)  # 롱런형 완화
        p.tal_d = 0.6
        self.assertLess(expected_delta(p, "contact", 38), -2.2)     # 급쇠퇴형 가중


class TestOffseasonTick(unittest.TestCase):
    def test_seed_reproducible(self):
        results = []
        for _ in range(2):
            teams = load_league()
            rng = random.Random(5)
            for y in range(3):
                offseason_tick(rng, teams, year=y)
            results.append(snapshot(teams))
        self.assertEqual(results[0], results[1])

    def test_clamps(self):
        teams = load_league()
        before = snapshot(teams)
        offseason_tick(random.Random(9), teams, year=1)
        a = TUNE["aging"]
        for t in teams:
            for p in t.roster:
                r = p.pit if p.is_pitcher else p.bat
                for k, v in vars(r).items():
                    self.assertGreaterEqual(v, a["rating_min"])
                    self.assertLessEqual(v, a["rating_max"])
                    if p.pid in before:  # 신인 제외
                        self.assertLessEqual(abs(v - before[p.pid][k]),
                                             a["delta_clamp"] + 1e-9)

    def test_forced_retirement_and_stub_replacement(self):
        teams = load_league()
        target = teams[0].roster[0]
        target.age = TUNE["aging"]["retire_age_hard"]  # 틱에서 +1 → 강제 은퇴
        n_before = len(teams[0].roster)
        pos = target.pos
        rep = offseason_tick(random.Random(3), teams, year=1)
        pids = {p.pid for p in teams[0].roster}
        self.assertNotIn(target.pid, pids)
        self.assertEqual(len(teams[0].roster), n_before)  # 1:1 유지
        self.assertIn(target.pid, {p.pid for _, p in rep.retired})
        stub = next(p for _, p in rep.rookies if p.team_id == teams[0].tid
                    and p.pos == pos)
        self.assertTrue(stub.stub)
        self.assertNotEqual(stub.tal_g, 0.0)  # 재능 추첨됨
        self.assertIn(stub.pid, pids)

    def test_potential_at_least_current(self):
        teams = load_league()
        offseason_tick(random.Random(2), teams, year=1)
        for t in teams:
            for p in t.roster:
                self.assertGreaterEqual(potential(p) + 1e-9, overall(p))

    def test_season_play_does_not_touch_ratings(self):
        """에이징은 시즌 간 전용 — 경기 시뮬은 능력치를 바꾸지 않는다 (회귀 가드)."""
        teams = load_league()
        before = snapshot(teams)
        GameSimulator(teams[0], teams[1], random.Random(1)).run()
        self.assertEqual(snapshot(teams), before)


if __name__ == "__main__":
    unittest.main()
