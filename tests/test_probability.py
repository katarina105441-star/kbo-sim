"""확률 수식 단위 검증 — 밸런스가 깨지는 수정을 잡아내는 안전망."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.models.player import Player, Contract, BatterRatings, PitcherRatings
from kbo.engine import probability as prob


def make_batter(v: float) -> Player:
    p = Player("T-B0", "평균타자", "T", "CF", 28, "R", "R", Contract(1, 1),
               bat=BatterRatings(*([int(v)] * 6)))
    prob.precompute_batter(p)
    return p


def make_pitcher(v: float) -> Player:
    p = Player("T-P0", "평균투수", "T", "SP", 28, "R", "R", Contract(1, 1),
               pit=PitcherRatings(*([int(v)] * 5)))
    prob.precompute_pitcher(p)
    return p


class TestLog5(unittest.TestCase):
    def test_anchor_players_hit_league_rates(self):
        """앵커 능력치 타자 × 앵커 투수 = 정확히 리그 기준율."""
        a = prob.TUNE["anchor"]
        b, p = make_batter(a), make_pitcher(a)
        probs = prob.pa_event_probs(b, p, fatigue=0.0, tto=1, same_hand=False)
        lg = prob.TUNE["lg"]
        self.assertAlmostEqual(probs["K"], lg["k"], places=6)
        self.assertAlmostEqual(probs["BB"], lg["bb"], places=6)
        self.assertAlmostEqual(probs["HR"], lg["hr"], places=6)
        self.assertAlmostEqual(probs["HBP"], lg["hbp"], places=6)

    def test_better_batter_better_outcomes(self):
        p = make_pitcher(prob.TUNE["anchor"])
        weak, strong = make_batter(35), make_batter(85)
        pw = prob.pa_event_probs(weak, p, fatigue=0, tto=1, same_hand=False)
        ps = prob.pa_event_probs(strong, p, fatigue=0, tto=1, same_hand=False)
        self.assertLess(ps["K"], pw["K"])
        self.assertGreater(ps["BB"], pw["BB"])
        self.assertGreater(ps["HR"], pw["HR"])

    def test_better_pitcher_suppresses(self):
        b = make_batter(prob.TUNE["anchor"])
        weak, ace = make_pitcher(35), make_pitcher(85)
        pw = prob.pa_event_probs(b, weak, fatigue=0, tto=1, same_hand=False)
        pa = prob.pa_event_probs(b, ace, fatigue=0, tto=1, same_hand=False)
        self.assertGreater(pa["K"], pw["K"])
        self.assertLess(pa["BB"], pw["BB"])
        self.assertLess(pa["HR"], pw["HR"])

    def test_platoon_penalty(self):
        """같은 손 매치업이면 타자 불리 (승인된 단순 플래툰)."""
        a = prob.TUNE["anchor"]
        b, p = make_batter(a), make_pitcher(a)
        neutral = prob.pa_event_probs(b, p, fatigue=0, tto=1, same_hand=False)
        same = prob.pa_event_probs(b, p, fatigue=0, tto=1, same_hand=True)
        self.assertGreater(same["K"], neutral["K"])
        self.assertLess(same["HR"], neutral["HR"])

    def test_fatigue_hurts_pitcher(self):
        a = prob.TUNE["anchor"]
        b, p = make_batter(a), make_pitcher(a)
        fresh = prob.pa_event_probs(b, p, fatigue=0.0, tto=1, same_hand=False)
        tired = prob.pa_event_probs(b, p, fatigue=0.4, tto=1, same_hand=False)
        self.assertLess(tired["K"], fresh["K"])
        self.assertGreater(tired["BB"], fresh["BB"])
        self.assertGreater(tired["HR"], fresh["HR"])

    def test_probs_sum_to_one(self):
        b, p = make_batter(95), make_pitcher(20)
        probs = prob.pa_event_probs(b, p, fatigue=0, tto=3, same_hand=False)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)
        self.assertGreaterEqual(probs["BIP"], 0.05)


if __name__ == "__main__":
    unittest.main()
