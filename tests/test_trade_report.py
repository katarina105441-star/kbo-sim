"""사용자 트레이드 결과의 오프시즌 리포트 변환 검증."""
from types import SimpleNamespace
import unittest

from kbo.io.loader import load_league
from kbo.models.team import DraftPick
from web.backend.draft_management import _trade_report


class TestTradeReport(unittest.TestCase):
    def test_player_and_pick_names_render_without_attribute_error(self):
        teams = load_league()
        player = teams[0].roster[0]
        pick = DraftPick(year=1, round=2, original_tid=teams[0].tid)
        market = SimpleNamespace(
            report=SimpleNamespace(trades=[]),
            user_trades=[SimpleNamespace(
                user_tid=teams[0].tid,
                other_tid=teams[1].tid,
                user_gave=[player],
                user_received=[pick],
            )],
        )
        report = _trade_report(market)
        self.assertEqual(report["stage"], "트레이드")
        self.assertIn(player.name, report["items"][0])
        self.assertIn("2R 지명권", report["items"][0])


if __name__ == "__main__":
    unittest.main()
