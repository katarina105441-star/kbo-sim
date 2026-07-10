"""FA 검증 — 자격/등급/보상금 이전/성향 가중/한도/다년계약 존속/회귀."""
import random
import unittest

from kbo.engine.game import GameSimulator
from kbo.engine.probability import TUNE
from kbo.io.loader import load_league
from kbo.league.economy import init_market, offseason_finance_tick
from kbo.league.fa import (assign_grades, compensation, eligible, player_weights,
                           run_fa_market, seed_service_years)
from kbo.league.season import SeasonRunner


def _prep(seed=1):
    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    rng = random.Random(seed)
    season = SeasonRunner(teams, rng)
    season.run()
    return teams, rng, season.standings()


class TestEligibilityAndGrades(unittest.TestCase):
    def test_seed_service_by_age(self):
        teams = load_league()
        seed_service_years(teams)
        vet = next(p for t in teams for p in t.roster if p.age >= 36)
        kid = next(p for t in teams for p in t.roster if p.age <= 24)
        self.assertTrue(vet.service_years >= 16)
        self.assertFalse(eligible(kid))

    def test_grades_split_thirds(self):
        teams = load_league()
        seed_service_years(teams)
        decl = [p for t in teams for p in t.roster][:30]
        assign_grades(decl)
        from collections import Counter
        c = Counter(p.fa_grade for p in decl)
        self.assertEqual(c["A"], 10)
        self.assertEqual(c["B"], 10)
        self.assertEqual(c["C"], 10)

    def test_compensation_by_grade(self):
        teams = load_league()
        p = teams[0].roster[0]
        p.contract.salary = 10.0
        p.fa_grade = "A"
        self.assertAlmostEqual(compensation(p), 30.0)   # A 300%
        p.fa_grade = "C"
        self.assertAlmostEqual(compensation(p), 15.0)   # C 150%


class TestAppealWeights(unittest.TestCase):
    def test_weights_sum_one_and_tilt(self):
        teams = load_league()
        rng = random.Random(2)
        vet = next(p for t in teams for p in t.roster if p.age >= 36)
        kid = next(p for t in teams for p in t.roster if p.age <= 26)
        for p in (vet, kid):
            w = player_weights(rng, p)
            self.assertAlmostEqual(sum(w), 1.0, places=6)
        # 편향 방향 (노이즈 평균화 위해 여러 번)
        ws_vet = [player_weights(random.Random(i), vet) for i in range(50)]
        ws_kid = [player_weights(random.Random(i), kid) for i in range(50)]
        avg = lambda ws, i: sum(w[i] for w in ws) / len(ws)
        self.assertGreater(avg(ws_vet, 2), avg(ws_kid, 2))   # 노장 +win
        self.assertGreater(avg(ws_kid, 1), avg(ws_vet, 1))   # 젊은 FA +play


class TestMarketMechanics(unittest.TestCase):
    def test_market_reproducible(self):
        res = []
        for _ in range(2):
            teams, rng, st = _prep(seed=3)
            rep = run_fa_market(rng, teams, st, year=1)
            res.append([(s.player.pid, s.to_tid, s.aav) for s in rep.signings])
        self.assertEqual(res[0], res[1])

    def test_comp_transferred_and_roster_moved(self):
        teams, rng, st = _prep(seed=5)
        budg = {t.tid: t.budget for t in teams}
        rep = run_fa_market(rng, teams, st, year=1)
        for m in rep.moved:
            self.assertEqual(m.player.team_id, m.to_tid)
            to_t = next(t for t in teams if t.tid == m.to_tid)
            self.assertIn(m.player, to_t.roster)
        if rep.moved:   # 보상금 순이동: 영입팀 예산↓ 원팀 예산↑ (총합 보존)
            self.assertAlmostEqual(sum(t.budget for t in teams),
                                   sum(budg.values()), places=1)

    def test_signing_limit(self):
        teams, rng, st = _prep(seed=7)
        rep = run_fa_market(rng, teams, st, year=1)
        limit = max(1, rep.declared // TUNE["fa"]["max_signings_divisor"])
        from collections import Counter
        c = Counter(m.to_tid for m in rep.moved)
        for tid, n in c.items():
            self.assertLessEqual(n, limit)

    def test_reeligibility_pushed(self):
        teams, rng, st = _prep(seed=5)
        rep = run_fa_market(rng, teams, st, year=1)
        for s in rep.signings:
            self.assertGreaterEqual(s.player.fa_eligible_at,
                                    s.player.service_years + TUNE["fa"]["reelig"] - 1e-9)


class TestRegression(unittest.TestCase):
    def test_multiyear_contract_survives_finance_tick(self):
        teams, rng, st = _prep(seed=5)
        rep = run_fa_market(rng, teams, st, year=1)
        multi = [s.player for s in rep.signings if s.player.contract.years > 1]
        if multi:
            p = multi[0]
            sal, yrs = p.contract.salary, p.contract.years
            offseason_finance_tick(rng, teams, year=1)
            self.assertEqual(p.contract.salary, sal)     # 연봉 고정
            self.assertEqual(p.contract.years, yrs - 1)  # 잔여 감소

    def test_season_play_unaffected(self):
        teams = load_league()
        r1 = GameSimulator(teams[0], teams[1], random.Random(1)).run().score
        teams2 = load_league()
        seed_service_years(teams2)   # FA 시딩이 경기와 무관함을 확인
        r2 = GameSimulator(teams2[0], teams2[1], random.Random(1)).run().score
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
