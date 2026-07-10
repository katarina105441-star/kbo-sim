"""MVP-3 Part 2A 경기 상태머신과 수동 투수 교체 검증."""
import pickle
import random
import unittest

from kbo.engine.game import GameSimulator
from kbo.io.loader import load_league


def teams_pair():
    teams = load_league()
    home = next(t for t in teams if t.tid == "KIA")
    away = next(t for t in teams if t.tid == "LG")
    return home, away


def fingerprint(result):
    return {
        "score": result.score,
        "line": result.line,
        "tie": result.tie,
        "innings": result.innings,
        "decisions": result.decisions,
        "stints": {
            side: [(st.player.pid, st.line.outs, st.line.pitches,
                    st.line.h, st.line.r, st.line.er, st.line.bb, st.line.so)
                   for st in result.stints[side]]
            for side in ("home", "away")
        },
        "bat": {
            side: [(p.pid, slot, line.pa, line.ab, line.h, line.hr,
                    line.r, line.rbi, line.bb, line.so, line.sb, line.cs)
                   for p, slot, line in result.box_bat[side]]
            for side in ("home", "away")
        },
        "events": result.struct_events,
    }


class TestLiveGameStateMachine(unittest.TestCase):
    def test_run_and_step_pa_are_identical(self):
        for seed in (1, 42, 2026, 90210):
            home1, away1 = teams_pair()
            auto = GameSimulator(home1, away1, random.Random(seed),
                                 record=False, record_struct=True).run()

            home2, away2 = teams_pair()
            stepped = GameSimulator(home2, away2, random.Random(seed),
                                    record=False, record_struct=True)
            stepped.start()
            guard = 0
            while not stepped.done:
                stepped.step_pa()
                guard += 1
                self.assertLess(guard, 500, f"seed {seed}: 경기 종료 실패")

            self.assertEqual(fingerprint(auto), fingerprint(stepped.result),
                             f"seed {seed}: run/step 결과 불일치")

    def test_manual_pitcher_change_applies_to_next_batter(self):
        home, away = teams_pair()
        sim = GameSimulator(home, away, random.Random(77),
                            record=False, record_struct=True)
        state = sim.start()
        self.assertEqual(state["fielding_side"], "home")
        pid = state["available_relievers"][0]["pid"]

        changed = sim.force_pitcher_change("home", pid)
        self.assertEqual(changed["pitcher"]["pid"], pid)
        out = sim.step_pa()
        pa = next(ev for ev in out["events"] if ev["t"] == "pa")
        self.assertEqual(pa["pitcher"]["pid"], pid)
        changes = [ev for ev in sim.struct_events if ev["t"] == "pitch_change"]
        self.assertEqual(changes[-1]["in"]["pid"], pid)

    def test_used_pitcher_cannot_reenter(self):
        home, away = teams_pair()
        sim = GameSimulator(home, away, random.Random(88), record=False)
        first = sim.start()["available_relievers"][0]["pid"]
        sim.force_pitcher_change("home", first)
        sim.step_pa()
        second = sim.state()["available_relievers"][0]["pid"]
        sim.force_pitcher_change("home", second)
        with self.assertRaisesRegex(ValueError, "재등판"):
            sim.force_pitcher_change("home", first)

    def test_invalid_manual_pitcher_changes_are_rejected(self):
        home, away = teams_pair()
        for team in (home, away):
            team.build_default_lineup()
            team.build_default_pitching()
        unavailable_pid = home.bullpen[0].pid
        unavailable = {unavailable_pid}
        sim = GameSimulator(home, away, random.Random(99), record=False,
                            home_unavailable=unavailable)
        sim.start()
        with self.assertRaisesRegex(ValueError, "수비 중인 팀"):
            sim.force_pitcher_change("away", away.bullpen[0].pid)
        with self.assertRaisesRegex(ValueError, "야수"):
            sim.force_pitcher_change("home", home.batters[0].pid)
        with self.assertRaisesRegex(ValueError, "등판할 수 없는"):
            sim.force_pitcher_change("home", unavailable_pid)
        with self.assertRaisesRegex(ValueError, "로스터에 없는"):
            sim.force_pitcher_change("home", away.bullpen[0].pid)

    def test_in_progress_game_is_pickle_serializable(self):
        home, away = teams_pair()
        sim = GameSimulator(home, away, random.Random(1234),
                            record=False, record_struct=True)
        sim.start()
        for _ in range(7):
            sim.step_pa()
        restored = pickle.loads(pickle.dumps(sim))
        self.assertEqual(restored.state(), sim.state())
        self.assertEqual(fingerprint(restored.finish_auto()),
                         fingerprint(sim.finish_auto()))


if __name__ == "__main__":
    unittest.main()
