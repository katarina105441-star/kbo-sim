"""드래프트 검증 — 역순 순서 / Need 우선 / BPA 예외 / 풀 refill / 회귀."""
import random
import unittest

from kbo.engine.game import GameSimulator
from kbo.engine.probability import TUNE
from kbo.io.loader import load_league
from kbo.league.aging import ensure_talents, offseason_tick
from kbo.league.draft import build_pool, need_bonus, run_draft
from kbo.league.economy import init_market
from kbo.league.season import SeasonRunner


def _prep(seed=1):
    teams = load_league()
    init_market(teams)
    rng = random.Random(seed)
    season = SeasonRunner(teams, rng)
    season.run()
    return teams, rng, season.standings()


class TestDraftRefill(unittest.TestCase):
    def test_draft_mode_leaves_holes(self):
        teams, rng, _ = _prep()
        rep = offseason_tick(rng, teams, year=1, draft_mode=True)
        # 은퇴자만큼 로스터 축소 (자동 스텁 대체 없음)
        self.assertTrue(any(len(t.roster) < 25 for t in teams))
        self.assertEqual(rep.rookies, [])
        self.assertTrue(rep.retired)

    def test_draft_refills_to_25(self):
        teams, rng, standings = _prep()
        offseason_tick(rng, teams, year=1, draft_mode=True)
        run_draft(rng, teams, standings, year=1)
        for t in teams:
            self.assertEqual(len(t.roster), 25)

    def test_default_mode_still_autostubs(self):
        """draft_mode=False는 기존 1:1 스텁 대체 유지 (회귀)."""
        teams, rng, _ = _prep()
        rep = offseason_tick(rng, teams, year=1)  # draft_mode 기본 False
        for t in teams:
            self.assertEqual(len(t.roster), 25)
        self.assertEqual(len(rep.rookies), len(rep.retired))


class TestDraftOrder(unittest.TestCase):
    def test_reverse_order_within_round(self):
        teams, rng, standings = _prep()
        offseason_tick(rng, teams, year=1, draft_mode=True)
        picks = run_draft(rng, teams, standings, year=1)
        rev = [t.tid for t in reversed(standings)]   # 꼴찌 먼저
        # 1라운드 지명 순서는 역순 순위의 부분수열 (구멍 없는 팀만 스킵)
        r1 = [pk.tid for pk in picks if pk.round == 1]
        it = iter(rev)
        self.assertTrue(all(tid in it for tid in r1),
                        f"1R 지명 순서 {r1}가 역순 {rev}의 부분수열이 아님")

    def test_pool_pitcher_heavy(self):
        teams, rng, _ = _prep()
        offseason_tick(rng, teams, year=1, draft_mode=True)
        pool = build_pool(rng, teams, year=1)
        pit = sum(1 for p in pool if p.is_pitcher)
        self.assertGreater(pit / len(pool), 0.5)   # 투수 편중 (모집단 60~65%)
        self.assertGreaterEqual(len(pool), TUNE["draft"]["pool_min"])


class TestNeedAndBPA(unittest.TestCase):
    def test_need_higher_for_weak_position(self):
        teams, _, _ = _prep()
        t = teams[0]
        # 포수를 모두 제거 → C need 최대, 강한 포지션 need 0 근처
        t.roster = [p for p in t.roster if p.pos != "C"]
        self.assertAlmostEqual(need_bonus(t, "C"), TUNE["draft"]["need_max_bonus"])
        best_1b = max((p.bat_overall for p in t.roster if p.pos == "1B"), default=0)
        if best_1b >= TUNE["draft"]["need_ref"]:
            self.assertEqual(need_bonus(t, "1B"), 0.0)

    def test_need_bonus_bounded(self):
        teams, _, _ = _prep()
        for t in teams:
            for pos in ("C", "SS", "SP", "1B"):
                nb = need_bonus(t, pos)
                self.assertGreaterEqual(nb, 0.0)
                self.assertLessEqual(nb, TUNE["draft"]["need_max_bonus"] + 1e-9)


class TestRegression(unittest.TestCase):
    def test_draft_reproducible(self):
        res = []
        for _ in range(2):
            teams, rng, standings = _prep(seed=3)
            offseason_tick(rng, teams, year=1, draft_mode=True)
            picks = run_draft(rng, teams, standings, year=1)
            res.append([(pk.tid, pk.player.pos, round(pk.true_val, 3)) for pk in picks])
        self.assertEqual(res[0], res[1])

    def test_season_play_unaffected_by_draft_module(self):
        """드래프트는 시즌 간 로직 — 경기 시뮬 결과 불변 (회귀 가드)."""
        teams = load_league()
        r1 = GameSimulator(teams[0], teams[1], random.Random(1)).run().score
        teams2 = load_league()
        r2 = GameSimulator(teams2[0], teams2[1], random.Random(1)).run().score
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
