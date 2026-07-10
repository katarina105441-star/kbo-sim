"""연봉/계약·재정 검증 — 가치 단조성 / 캡 산정 / 런어웨이 클램프 / 시즌 중 무변화."""
import random
import unittest

from kbo.engine.game import GameSimulator
from kbo.engine.probability import TUNE
from kbo.io.loader import load_league
from kbo.league.aging import ensure_talents
from kbo.league import contracts as C
from kbo.league.economy import (init_market, league_cap, offseason_finance_tick,
                                team_payroll, update_budget, _budget_target)


def _prep():
    teams = load_league()
    init_market(teams)
    ensure_talents(random.Random(1), (p for t in teams for p in t.roster))
    return teams


class TestValuation(unittest.TestCase):
    def test_cap_grows_5pct(self):
        self.assertAlmostEqual(league_cap(0), 137.0)
        self.assertAlmostEqual(league_cap(1), 137.0 * 1.05)

    def test_young_has_higher_asset_than_old_same_ovr(self):
        """같은 OVR·역할이면 젊을수록 asset_war(잔여 전성기)가 크다."""
        teams = _prep()
        # 확실히 대체선수 이상인 선수 (repl 조정에도 두 나이 모두 WAR>0 보장)
        p = max((x for t in teams for x in t.roster if not x.is_pitcher),
                key=lambda x: x.bat_overall)
        p.tal_g, p.tal_d = 1.0, 1.0
        p.age = 24
        young = C.asset_war(p, 1.0)
        p.age = 34
        old = C.asset_war(p, 1.0)
        self.assertGreater(young, old)

    def test_fair_salary_floor(self):
        """대체선수 이하도 최저연봉 바닥은 받는다."""
        teams = _prep()
        p = min((x for t in teams for x in t.roster if not x.is_pitcher),
                key=lambda x: x.bat_overall)
        p.bat.contact = p.bat.power = p.bat.eye = 20
        p.bat.speed = p.bat.fielding = p.bat.arm = 20
        self.assertGreaterEqual(C.fair_salary(p, 137.0, 0.3),
                                TUNE["contract"]["min_salary"])

    def test_value_of_dispatch(self):
        from kbo.models.team import DraftPick
        teams = _prep()
        p = teams[0].roster[0]
        self.assertGreater(C.value_of(p, 137.0, 1.0), 0)
        # 지명권: 라운드 높을수록 가치↑, 페널티 지명권 할인 (트레이드 단계 구현)
        r1 = C.value_of(DraftPick(2026, 1, "KIA"), 137.0)
        r3 = C.value_of(DraftPick(2026, 3, "KIA"), 137.0)
        pen = C.value_of(DraftPick(2026, 1, "KIA", penalty=True), 137.0)
        self.assertGreater(r1, r3)
        self.assertLess(pen, r1)


class TestBudgetDynamics(unittest.TestCase):
    def test_update_budget_clamped_to_cap_and_floor(self):
        cap = 137.0
        floor = cap * TUNE["contract"]["floor_frac"]
        # 목표가 캡보다 커도 캡 초과 못 함
        self.assertLessEqual(update_budget(130, 500, cap), cap + 1e-9)
        # 목표가 0이어도 하한 밑으로 못 감
        self.assertGreaterEqual(update_budget(70, 0, cap), floor - 1e-9)

    def test_max_swing_limits_single_season_move(self):
        cap = 137.0
        prev = 100.0
        moved = update_budget(prev, 137.0, cap)   # 목표는 캡이지만
        self.assertLessEqual(moved, prev * (1 + TUNE["contract"]["max_swing"]) + 1e-9)

    def test_dynamic_dominates_market(self):
        """성적 변동폭이 시장차보다 커야 한다 (짠물 우승 > 큰손 꼴찌)."""
        teams = _prep()
        cap = league_cap(0)
        big, small = teams[0], teams[1]
        big.market_size, small.market_size = 1.15, 0.90
        big.wins, small.wins = 55, 95        # 큰손 꼴찌 vs 짠물 우승
        self.assertGreater(_budget_target(small, cap), _budget_target(big, cap))


class TestRegression(unittest.TestCase):
    def test_finance_tick_reproducible(self):
        res = []
        for _ in range(2):
            teams = load_league()
            init_market(teams)
            rng = random.Random(4)
            offseason_finance_tick(rng, teams, year=1)
            res.append([round(p.contract.salary, 3)
                        for t in teams for p in t.roster])
        self.assertEqual(res[0], res[1])

    def test_season_play_does_not_touch_salary_or_budget(self):
        """계약/예산은 시즌 간 로직 — 경기 시뮬은 건드리지 않는다 (회귀 가드)."""
        teams = _prep()
        init_market(teams)
        sal = {p.pid: p.contract.salary for t in teams for p in t.roster}
        budg = {t.tid: t.budget for t in teams}
        GameSimulator(teams[0], teams[1], random.Random(1)).run()
        self.assertEqual({p.pid: p.contract.salary
                          for t in teams for p in t.roster}, sal)
        self.assertEqual({t.tid: t.budget for t in teams}, budg)


if __name__ == "__main__":
    unittest.main()
