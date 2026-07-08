"""트레이드 검증 — 3조건 결렬 / 지명권 민팅·이동·행사 / 재현성 / 회귀."""
import random
import unittest

from kbo.engine.game import GameSimulator
from kbo.engine.probability import TUNE
from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick
from kbo.league.draft import run_draft
from kbo.league.economy import init_market
from kbo.league.fa import seed_service_years
from kbo.league.trade import (GMView, mint_picks, run_trades, team_phase,
                              tradable_prospects, _try_pair)
from kbo.league.season import SeasonRunner


def _prep(seed=1):
    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    rng = random.Random(seed)
    season = SeasonRunner(teams, rng)
    season.run()
    return teams, rng, season.standings()


class TestPhase(unittest.TestCase):
    def test_phase_thresholds(self):
        self.assertEqual(team_phase(1, 10), "win")
        self.assertEqual(team_phase(5, 10), "mid")
        self.assertEqual(team_phase(10, 10), "rebuild")


class TestPicks(unittest.TestCase):
    def test_mint_three_rounds(self):
        teams = load_league()
        mint_picks(teams, year=3)
        for t in teams:
            self.assertEqual(len(t.draft_picks), TUNE["trade"]["mint_rounds"])
            self.assertTrue(all(pk.year == 3 and pk.original_tid == t.tid
                                for pk in t.draft_picks))

    def test_traded_pick_exercised_by_owner(self):
        """지명권 이동 시 슬롯 순서는 유지, 행사는 보유팀."""
        teams, rng, st = _prep()
        offseason_tick(rng, teams, year=1, draft_mode=True)
        mint_picks(teams, year=1)
        worst, champ = st[-1], st[0]
        # 꼴찌의 1R 지명권을 우승팀으로 이동 + 우승팀에 구멍 확보
        pk = next(p for p in worst.draft_picks if p.round == 1)
        worst.draft_picks.remove(pk)
        champ.draft_picks.append(pk)
        if len(champ.roster) >= 25:
            champ.roster.pop()
        picks = run_draft(rng, teams, st, year=1)
        first = picks[0]                      # 첫 슬롯 = 꼴찌 자리
        self.assertEqual(first.round, 1)
        self.assertEqual(first.tid, champ.tid)   # 행사자는 보유팀(우승팀)


class TestThreeConditions(unittest.TestCase):
    def test_no_prospects_fails(self):
        """(b) 니즈: 윈나우에 잉여 유망주가 없으면 결렬."""
        teams, rng, st = _prep()
        mint_picks(teams, year=1)
        phases = {t.tid: "win" if t is st[0] else "rebuild" for t in teams}
        gm = GMView(rng, 137.0, 1, phases)
        win = st[0]
        win.roster = [p for p in win.roster
                      if p.age > TUNE["trade"]["young_age"]]   # 유망주 제거
        self.assertIsNone(_try_pair(gm, win, st[-1]))

    def test_equivalence_rejection(self):
        """(a) 등가: tol·노이즈·시간선호를 전부 끄면 정확 등가 요구 → 전부 결렬.

        (시간 선호가 켜져 있으면 tol=0·노이즈=0이어도 양쪽 모두 잉여가 생겨
        거래가 성사된다 — 그게 설계 의도. 여기선 잉여의 원천을 다 꺼서
        '이득 없는 거래는 성사되지 않는다'는 결렬 로직 자체를 검증.)
        """
        teams, rng, st = _prep()
        mint_picks(teams, year=1)
        tr = TUNE["trade"]
        saved = {k: tr[k] for k in ("tol", "gm_noise", "disc_win", "disc_reb",
                                    "pick_mult_win", "pick_mult_reb")}
        tr.update({"tol": 0.0, "gm_noise": 0.0,
                   "disc_win": TUNE["contract"]["discount"],
                   "disc_reb": TUNE["contract"]["discount"],
                   "pick_mult_win": 1.0, "pick_mult_reb": 1.0})
        try:
            rep = run_trades(rng, teams, st, year=1)
            self.assertEqual(len(rep.trades), 0)   # 정확 등가는 사실상 불가
            self.assertGreater(rep.attempted, 0)
        finally:
            tr.update(saved)

    def test_complementarity_only_win_rebuild(self):
        """(c) 상보성: 성사 거래는 전부 윈나우←즉전 / 리빌딩←유망주 방향."""
        teams, rng, st = _prep(seed=7)
        offseason_tick(rng, teams, year=1, draft_mode=True)
        rep = run_trades(rng, teams, st, year=1)
        n = len(teams)
        rank = {t.tid: i for i, t in enumerate(st, 1)}
        for d in rep.trades:
            self.assertEqual(team_phase(rank[d.win_tid], n), "win")
            self.assertEqual(team_phase(rank[d.reb_tid], n), "rebuild")
            self.assertGreaterEqual(d.veteran.age, TUNE["trade"]["vet_age"])
            for p in d.prospects:
                self.assertLessEqual(p.age, TUNE["trade"]["young_age"])


class TestRegression(unittest.TestCase):
    def test_trades_reproducible(self):
        res = []
        for _ in range(2):
            teams, rng, st = _prep(seed=7)
            offseason_tick(rng, teams, year=1, draft_mode=True)
            rep = run_trades(rng, teams, st, year=1)
            res.append([(d.win_tid, d.reb_tid, d.veteran.pid) for d in rep.trades])
        self.assertEqual(res[0], res[1])

    def test_roster_counts_preserved(self):
        teams, rng, st = _prep(seed=7)
        offseason_tick(rng, teams, year=1, draft_mode=True)
        sizes = {t.tid: len(t.roster) for t in teams}
        run_trades(rng, teams, st, year=1)   # 선수 1↔1 교환이라 인원 불변
        self.assertEqual({t.tid: len(t.roster) for t in teams}, sizes)

    def test_season_play_unaffected(self):
        teams = load_league()
        r1 = GameSimulator(teams[0], teams[1], random.Random(1)).run().score
        teams2 = load_league()
        mint_picks(teams2, year=1)   # 지명권 민팅이 경기와 무관함을 확인
        r2 = GameSimulator(teams2[0], teams2[1], random.Random(1)).run().score
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
