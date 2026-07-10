"""사용자 참여 트레이드 시장 검증."""
import pickle
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.economy import init_market
from kbo.league.fa import seed_service_years
from kbo.league.trade_session import InteractiveTradeMarket


def prepared(seed=1):
    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    rng = random.Random(seed)
    return teams, rng, list(teams)


def pick_id(team, rnd):
    pick = next(p for p in team.draft_picks if p.round == rnd)
    return f"D:{pick.year}:{pick.round}:{pick.original_tid}"


class TestInteractiveTradeMarket(unittest.TestCase):
    def test_user_excluded_from_automatic_ai_trades(self):
        teams, rng, standings = prepared(7)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        for deal in market.report.trades:
            self.assertNotEqual(deal.win_tid, "KIA")
            self.assertNotEqual(deal.reb_tid, "KIA")
        self.assertEqual(len(market.user_team.draft_picks), 3)

    def test_favorable_pick_swap_is_accepted_and_assets_move(self):
        teams, rng, standings = prepared(11)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        other = next(t for t in teams if t.tid != "KIA")
        give_id = pick_id(market.user_team, 1)
        receive_id = pick_id(other, 3)

        result = market.propose(other.tid, [give_id], [receive_id])

        self.assertEqual(result["status"], "accepted")
        self.assertIsNotNone(market._find_asset(other, give_id))
        self.assertIsNotNone(market._find_asset(market.user_team, receive_id))
        self.assertEqual(len(market.user_trades), 1)

    def test_extreme_underpay_is_rejected_without_moving_assets(self):
        teams, rng, standings = prepared(13)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        other = next(t for t in teams if t.tid != "KIA")
        give_id = pick_id(market.user_team, 3)
        target = max(other.roster, key=lambda p: market.gm.value(other.tid, p))
        receive_id = f"P:{target.pid}"

        result = market.propose(other.tid, [give_id], [receive_id])

        self.assertEqual(result["status"], "rejected")
        self.assertIsNotNone(market._find_asset(market.user_team, give_id))
        self.assertIsNotNone(market._find_asset(other, receive_id))

    def test_near_offer_can_generate_and_accept_counter(self):
        teams, rng, standings = prepared(17)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        found = None
        threshold = 0.90
        user_assets = market.user_team.roster + market.user_team.draft_picks
        for other in teams:
            if other.tid == "KIA":
                continue
            for give in user_assets:
                for receive in other.roster + other.draft_picks:
                    _recv, _give, ratio = market._ai_ratio(other, [give], [receive])
                    if 0.55 <= ratio < threshold:
                        counter = market._make_counter(other, [give], [receive])
                        if counter is not None:
                            found = (other, give, receive)
                            break
                if found:
                    break
            if found:
                break
        self.assertIsNotNone(found, "역제안 가능한 가치 구간의 자산 조합이 필요합니다.")
        other, give, receive = found

        result = market.propose(
            other.tid, [market._asset_id(give)], [market._asset_id(receive)])
        self.assertEqual(result["status"], "counter")
        self.assertIsNotNone(market.pending_counter)

        accepted = market.accept_counter()
        self.assertEqual(accepted["status"], "counter_accepted")
        self.assertIsNone(market.pending_counter)
        self.assertEqual(len(market.user_trades), 1)

    def test_invalid_or_duplicate_assets_are_rejected(self):
        teams, rng, standings = prepared(19)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        other = next(t for t in teams if t.tid != "KIA")
        give_id = pick_id(market.user_team, 1)
        receive_id = pick_id(other, 3)
        with self.assertRaisesRegex(ValueError, "중복"):
            market.propose(other.tid, [give_id, give_id], [receive_id])
        with self.assertRaisesRegex(ValueError, "보유하지 않은"):
            market.propose(other.tid, ["P:not-found"], [receive_id])

    def test_pickle_restores_negotiation_state_and_rng(self):
        teams, rng, standings = prepared(23)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        restored = pickle.loads(pickle.dumps(market))
        self.assertEqual(restored.state(), market.state())
        self.assertEqual(restored.rng.random(), market.rng.random())

    def test_finish_closes_market(self):
        teams, rng, standings = prepared(29)
        market = InteractiveTradeMarket(rng, teams, standings, 1, "KIA")
        result = market.finish()
        self.assertEqual(result["status"], "complete")
        self.assertTrue(market.complete)
        self.assertFalse(market.state()["active"])
        with self.assertRaises(RuntimeError):
            market.finish()


if __name__ == "__main__":
    unittest.main()
