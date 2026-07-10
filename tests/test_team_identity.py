"""구단별 감독·스카우팅·운영 성향 검증."""
import copy
import random
import unittest

from kbo.io.loader import load_league
from kbo.league.team_identity import (
    PROFILES,
    draft_fit_bonus,
    effective_phase,
    ensure_team_identities,
    fa_offer_multiplier,
    identity_payload,
    scouting_sigma,
    trade_asset_multiplier,
)


class TestTeamIdentity(unittest.TestCase):
    def setUp(self):
        self.teams = load_league()
        ensure_team_identities(self.teams)
        self.by_tid = {team.tid: team for team in self.teams}

    def test_all_teams_receive_stable_profiles(self):
        self.assertEqual(set(self.by_tid), set(PROFILES))
        self.assertEqual(len({team.identity.key for team in self.teams}), 10)
        for team in self.teams:
            payload = identity_payload(team)
            self.assertIn(payload["strategy"], {"win_now", "balanced", "rebuild"})
            self.assertTrue(payload["label"])
            self.assertTrue(payload["description"])

    def test_long_term_strategy_shifts_effective_phase(self):
        kia = self.by_tid["KIA"]
        sam = self.by_tid["SAM"]
        # 같은 중하위권 순위라도 윈나우 구단은 버티고, 재건 구단은 매도 단계로 간다.
        self.assertEqual(effective_phase(kia, 7, 10), "mid")
        self.assertEqual(effective_phase(sam, 7, 10), "rebuild")
        self.assertEqual(effective_phase(kia, 5, 10), "win")

    def test_scouting_strength_reduces_observation_noise(self):
        base = 0.25
        kt = self.by_tid["KT"]
        hwe = self.by_tid["HWE"]
        self.assertLess(scouting_sigma(kt, base), scouting_sigma(hwe, base))

    def _batter(self):
        player = copy.deepcopy(next(p for p in self.by_tid["KIA"].roster
                                    if not p.is_pitcher))
        for name in ("contact", "power", "eye", "speed", "fielding", "arm"):
            setattr(player.bat, name, 55.0)
        player.age = 21
        return player

    def test_draft_style_changes_player_fit(self):
        power_hitter = self._batter()
        power_hitter.bat.power = 92.0
        power_hitter.bat.contact = 42.0
        contact_hitter = copy.deepcopy(power_hitter)
        contact_hitter.bat.power = 42.0
        contact_hitter.bat.contact = 92.0
        contact_hitter.bat.eye = 85.0

        self.assertGreater(
            draft_fit_bonus(self.by_tid["SSG"], power_hitter, 2),
            draft_fit_bonus(self.by_tid["LTE"], power_hitter, 2),
        )
        self.assertGreater(
            draft_fit_bonus(self.by_tid["LTE"], contact_hitter, 2),
            draft_fit_bonus(self.by_tid["SSG"], contact_hitter, 2),
        )

    def test_rebuilding_team_values_young_asset_more(self):
        young = self._batter()
        young.team_id = "KIA"
        sam_value = trade_asset_multiplier(self.by_tid["SAM"], young, "rebuild")
        ssg_value = trade_asset_multiplier(self.by_tid["SSG"], young, "win")
        self.assertGreater(sam_value, ssg_value)

    def test_fa_aggression_changes_offer_multiplier(self):
        slugger = self._batter()
        slugger.age = 29
        slugger.bat.power = 90.0
        self.assertGreater(
            fa_offer_multiplier(self.by_tid["SSG"], slugger),
            fa_offer_multiplier(self.by_tid["SAM"], slugger),
        )

    def test_identity_is_pickle_safe(self):
        import pickle
        restored = pickle.loads(pickle.dumps(self.by_tid["KT"]))
        self.assertEqual(restored.identity, self.by_tid["KT"].identity)


if __name__ == "__main__":
    unittest.main()
