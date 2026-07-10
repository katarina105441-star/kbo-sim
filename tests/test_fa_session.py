"""중단 가능한 사용자 참여 FA 시장 검증."""
import pickle
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.economy import init_market
from kbo.league.fa import run_fa_market, seed_service_years
from kbo.league.fa_session import InteractiveFAMarket


def prepared(seed=1):
    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    return teams, random.Random(seed), list(teams)


def fp(report):
    return [(s.player.pid, s.from_tid, s.to_tid, s.grade, s.aav,
             s.fair, s.comp, s.n_offers)
            for s in report.signings]


class TestInteractiveFAMarket(unittest.TestCase):
    def test_auto_finish_matches_existing_market(self):
        teams1, rng1, standings1 = prepared(2026)
        expected = run_fa_market(rng1, teams1, standings1, year=1)

        teams2, rng2, standings2 = prepared(2026)
        market = InteractiveFAMarket(rng2, teams2, standings2, 1, "KIA")
        market.auto_finish()

        self.assertEqual(fp(expected), fp(market.report))
        self.assertEqual(
            [(t.tid, round(t.budget, 2), sorted(p.pid for p in t.roster)) for t in teams1],
            [(t.tid, round(t.budget, 2), sorted(p.pid for p in t.roster)) for t in teams2],
        )

    def test_high_user_offer_can_be_accepted_and_moves_player(self):
        teams, rng, standings = prepared(44)
        market = InteractiveFAMarket(rng, teams, standings, 1, "KIA")
        state = market.state()
        self.assertTrue(state["active"])
        player = state["player"]
        maximum = state["market"]["max_offer"]
        self.assertGreater(maximum, 0)

        result = market.offer(maximum)

        if result["accepted_user_offer"]:
            self.assertEqual(result["to_tid"], "KIA")
            kia = next(t for t in teams if t.tid == "KIA")
            self.assertTrue(any(p.pid == player["pid"] for p in kia.roster))
        self.assertTrue(result["user_offered"])

    def test_offer_above_limit_rejected_without_advancing(self):
        teams, rng, standings = prepared(55)
        market = InteractiveFAMarket(rng, teams, standings, 1, "KIA")
        before = market.state()
        with self.assertRaisesRegex(ValueError, "최대 AAV"):
            market.offer(before["market"]["max_offer"] + 1.0)
        self.assertEqual(market.state()["player"]["pid"], before["player"]["pid"])

    def test_pass_removes_user_bid_and_advances(self):
        teams, rng, standings = prepared(66)
        market = InteractiveFAMarket(rng, teams, standings, 1, "KIA")
        before_pid = market.state()["player"]["pid"]
        result = market.pass_player()
        self.assertFalse(result["user_offered"])
        self.assertEqual(result["pid"], before_pid)
        if not market.complete:
            self.assertNotEqual(market.state()["player"]["pid"], before_pid)

    def test_pickle_restores_pending_player_and_rng(self):
        teams, rng, standings = prepared(77)
        market = InteractiveFAMarket(rng, teams, standings, 1, "KIA")
        market.auto_resolve()
        restored = pickle.loads(pickle.dumps(market))
        self.assertEqual(restored.state(), market.state())
        self.assertEqual(restored.auto_resolve(), market.auto_resolve())

    def test_state_hides_player_preferences_and_ai_bid_amounts(self):
        teams, rng, standings = prepared(88)
        state = InteractiveFAMarket(rng, teams, standings, 1, "KIA").state()
        self.assertNotIn("weights", state)
        self.assertNotIn("ai_offers", state)
        self.assertIn("competitors", state["market"])
        self.assertIn("fair_aav", state["market"])


if __name__ == "__main__":
    unittest.main()
