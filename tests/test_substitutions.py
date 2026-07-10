"""MVP-3 Part 2B 대타·대주자·대수비 검증."""
import random
import unittest

from kbo.engine.baserunning import Runner
from kbo.engine.game import GameSimulator
from kbo.engine.substitution_patch import apply_substitution_patch
from kbo.io.loader import load_league

apply_substitution_patch()


def pair():
    teams = load_league()
    home = next(t for t in teams if t.tid == "KIA")
    away = next(t for t in teams if t.tid == "LG")
    return home, away


class TestSubstitutions(unittest.TestCase):
    def make(self, seed=42, record=False):
        home, away = pair()
        sim = GameSimulator(home, away, random.Random(seed), record=record,
                            record_struct=True)
        sim.start()
        return home, away, sim

    def test_pinch_hitter_bats_next_and_lineup_is_not_persisted(self):
        home, away, sim = self.make(11)
        season_lineup = [(p.pid, slot) for p, slot in away.lineup]
        old_pid = sim.state()["next_batter"]["pid"]
        bench = sim.state()["batting_substitutions"]["bench"]
        self.assertTrue(bench)
        new_pid = bench[0]["pid"]

        state = sim.force_pinch_hitter("away", new_pid)
        self.assertEqual(state["next_batter"]["pid"], new_pid)
        out = sim.step_pa()
        pa = next(ev for ev in out["events"] if ev["t"] == "pa")
        self.assertEqual(pa["batter"]["pid"], new_pid)
        sub = next(ev for ev in sim.struct_events if ev["t"] == "substitution")
        self.assertEqual(sub["kind"], "pinch_hitter")
        self.assertEqual(sub["out"]["pid"], old_pid)
        self.assertEqual([(p.pid, slot) for p, slot in away.lineup], season_lineup)

    def test_pinch_runner_preserves_responsible_pitcher(self):
        _home, away, sim = self.make(12)
        old = sim.subs.lineup("away")[0][0]
        responsible = sim.staff["home"].current
        sim.bases.slots[0] = Runner(old, responsible, earned=False)
        sim.bo["away"] = 1
        bench = sim.state()["batting_substitutions"]["bench"]
        new_pid = bench[0]["pid"]

        sim.force_pinch_runner("away", 1, new_pid)
        runner = sim.bases.first
        self.assertEqual(runner.player.pid, new_pid)
        self.assertIs(runner.resp_pitcher, responsible)
        self.assertFalse(runner.earned)
        active_pids = [p.pid for p, _ in sim.subs.lineup("away")]
        self.assertIn(new_pid, active_pids)
        self.assertNotIn(old.pid, active_pids)
        self.assertEqual(len(away.lineup), 9)

    def test_defensive_sub_recalculates_defense_and_keeps_batting_order(self):
        home, _away, sim = self.make(13)
        before_order = [p.pid for p, _ in sim.subs.lineup("home")]
        before_def = sim.defense["home"]
        bench = sim.subs.bench("home")
        target = None
        for i, (old, slot) in enumerate(sim.subs.lineup("home")):
            if slot == "DH":
                continue
            replacement = next((p for p in bench if p.pos == slot), None)
            if replacement:
                target = (i, old, slot, replacement)
                break
        self.assertIsNotNone(target, "동일 주 포지션 대수비 후보가 필요합니다.")
        idx, old, slot, replacement = target

        sim.force_defensive_sub("home", old.pid, replacement.pid)
        after = sim.subs.lineup("home")
        self.assertEqual(after[idx][0].pid, replacement.pid)
        self.assertEqual(after[idx][1], slot)
        self.assertNotEqual(sim.defense["home"], before_def)
        expected = before_order[:]
        expected[idx] = replacement.pid
        self.assertEqual([p.pid for p, _ in after], expected)
        self.assertNotEqual([p.pid for p, _ in home.lineup], expected)

    def test_removed_player_and_substitute_both_appear_in_boxscore(self):
        _home, _away, sim = self.make(14)
        old_pid = sim.state()["next_batter"]["pid"]
        new_pid = sim.state()["batting_substitutions"]["bench"][0]["pid"]
        sim.force_pinch_hitter("away", new_pid)
        result = sim.finish_auto()
        pids = [p.pid for p, _slot, _line in result.box_bat["away"]]
        self.assertIn(old_pid, pids)
        self.assertIn(new_pid, pids)

    def test_used_player_cannot_reenter(self):
        _home, _away, sim = self.make(15)
        bench = sim.state()["batting_substitutions"]["bench"]
        first, second = bench[0]["pid"], bench[1]["pid"]
        sim.force_pinch_hitter("away", first)
        sim.force_pinch_hitter("away", second)
        with self.assertRaisesRegex(ValueError, "재출전"):
            sim.force_pinch_hitter("away", first)

    def test_no_substitution_keeps_seed_result_and_team_lineups(self):
        home1, away1 = pair()
        before1 = {t.tid: [(p.pid, s) for p, s in t.lineup] for t in (home1, away1)}
        r1 = GameSimulator(home1, away1, random.Random(2026),
                           record=False, record_struct=True).run()
        home2, away2 = pair()
        r2 = GameSimulator(home2, away2, random.Random(2026),
                           record=False, record_struct=True).run()
        self.assertEqual((r1.score, r1.line, r1.decisions, r1.struct_events),
                         (r2.score, r2.line, r2.decisions, r2.struct_events))
        self.assertEqual(before1,
                         {t.tid: [(p.pid, s) for p, s in t.lineup]
                          for t in (home1, away1)})


if __name__ == "__main__":
    unittest.main()
