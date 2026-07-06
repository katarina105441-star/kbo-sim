"""경기 불변식 검증 — 점수/기록 정합성."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.engine.game import GameSimulator


class TestGame(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teams = load_league()

    def _sim(self, seed, record=False):
        rng = random.Random(seed)
        return GameSimulator(self.teams[0], self.teams[1], rng, record=record).run()

    def test_reproducible(self):
        r1, r2 = self._sim(7), self._sim(7)
        self.assertEqual(r1.score, r2.score)
        self.assertEqual(r1.line, r2.line)

    def test_invariants_over_many_games(self):
        for seed in range(60):
            res = self._sim(seed)
            a, h = res.score
            # 라인스코어 합 == 최종 점수
            self.assertEqual(sum(v for v in res.line["away"] if v), a)
            self.assertEqual(sum(v for v in res.line["home"] if v), h)
            # 득점 == 타자 득점 합 == 투수 실점 합
            for side, opp in (("away", "home"), ("home", "away")):
                s = a if side == "away" else h
                self.assertEqual(sum(bl.r for _, _, bl in res.box_bat[side]), s)
                self.assertEqual(sum(st.line.r for st in res.stints[opp]), s)
                # 타점 <= 득점 (병살 득점 불인정으로 항상 성립)
                self.assertLessEqual(sum(bl.rbi for _, _, bl in res.box_bat[side]), s)
            # 무승부가 아니면 승/패 투수 존재, 서로 다른 팀
            if not res.tie:
                self.assertIsNotNone(res.decisions["W"])
                self.assertIsNotNone(res.decisions["L"])
                win_side = "home" if h > a else "away"
                w_pids = {st.player.pid for st in res.stints[win_side]}
                l_pids = {st.player.pid for st in res.stints["away" if win_side == "home" else "home"]}
                self.assertIn(res.decisions["W"], w_pids)
                self.assertIn(res.decisions["L"], l_pids)
            # 수비팀 아웃카운트: 정규 종료 반이닝은 3의 배수 근처 (끝내기 예외)
            self.assertGreaterEqual(res.innings, 9)
            self.assertLessEqual(res.innings, 12)

    def test_outs_accounting(self):
        """홈팀이 끝까지 수비한 이닝 수 × 3 == 홈팀 투수 아웃 합 (끝내기/9말생략 감안해 원정 기준으로 검증)."""
        for seed in range(30):
            res = self._sim(seed)
            # 원정팀의 공격 이닝은 전부 3아웃으로 종료된다
            away_outs = sum(st.line.outs for st in res.stints["home"])
            n_innings = len(res.line["away"])
            self.assertEqual(away_outs, n_innings * 3)

    def test_season_recording(self):
        rng = random.Random(3)
        t0, t1 = self.teams[2], self.teams[3]
        for p in t0.roster + t1.roster:
            p.reset_season()
        t0.wins = t0.losses = t0.ties = 0
        t1.wins = t1.losses = t1.ties = 0
        res = GameSimulator(t0, t1, rng, record=True).run()
        a, h = res.score
        self.assertEqual(sum(p.season_bat.r for p in t0.roster), h)
        self.assertEqual(sum(p.season_bat.r for p in t1.roster), a)
        self.assertEqual(t0.wins + t0.losses + t0.ties, 1)


if __name__ == "__main__":
    unittest.main()
