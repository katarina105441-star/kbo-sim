"""관전 스트림 검증 — ★기록 ON/OFF 결과 불변 / 이벤트 폴드=박스스코어 / 재현성.

기록이 시뮬 결과를 미세하게라도 바꾸면 3단계에서 검증한 모든 것(리그 횡보·
순위 순환·트레이드 균형)이 무효가 된다 — 이 파일이 그 생명줄 가드다.
"""
import random
import unittest
from collections import Counter

from kbo.engine.game import GameSimulator
from kbo.io.loader import load_league
from kbo.league.season import SeasonRunner


def game_pair(seed, record_struct):
    teams = load_league()
    return GameSimulator(teams[0], teams[1], random.Random(seed),
                         record_struct=record_struct).run()


def season_fingerprint(teams, season):
    """승패 + 순위 + 개인기록 전체 지문."""
    fp = [(t.tid, t.wins, t.ties, t.losses) for t in season.standings()]
    for t in teams:
        for p in sorted(t.roster, key=lambda x: x.pid):
            b, pi = p.season_bat, p.season_pit
            fp.append((p.pid, b.pa, b.h, b.hr, b.rbi, b.sb,
                       pi.outs, pi.so, pi.w, pi.sv, pi.er))
    return fp


class TestOnOffInvariance(unittest.TestCase):
    """★최우선 — 기록은 순수 관측: ON/OFF가 결과를 절대 바꾸지 않는다."""

    def test_single_game_identical(self):
        for seed in (1, 7, 42):
            r_off = game_pair(seed, False)
            r_on = game_pair(seed, True)
            self.assertEqual(r_off.score, r_on.score, f"seed {seed} 점수 상이!")
            self.assertEqual(r_off.line, r_on.line)
            self.assertEqual(
                [(bl.h, bl.hr, bl.rbi) for s in ("away", "home")
                 for _, _, bl in r_off.box_bat[s]],
                [(bl.h, bl.hr, bl.rbi) for s in ("away", "home")
                 for _, _, bl in r_on.box_bat[s]])
            self.assertTrue(r_on.struct_events)      # ON은 실제로 기록됨
            self.assertEqual(r_off.struct_events, [])

    def test_full_season_identical_multi_seed(self):
        """시즌 전체: 승패·순위·개인기록 전부 동일 (여러 시드 교차)."""
        for seed in (11, 2026):
            fps = []
            for watch in (set(), {"KIA"}):
                teams = load_league()
                season = SeasonRunner(teams, random.Random(seed))
                season.record_watch = watch
                season.run()
                fps.append(season_fingerprint(teams, season))
            self.assertEqual(fps[0], fps[1], f"seed {seed}: 기록 ON/OFF 결과 상이!")

    def test_seed_2026_kia_97(self):
        """앵커 재확인: seed 2026 = KIA 97승 (관전 기록 켠 상태에서도)."""
        teams = load_league()
        season = SeasonRunner(teams, random.Random(2026))
        season.record_watch = {"KIA"}
        season.run()
        top = season.standings()[0]
        self.assertEqual((top.tid, top.wins), ("KIA", 97))


class TestStreamConsistency(unittest.TestCase):
    def test_fold_matches_boxscore(self):
        """이벤트 폴드(득점·아웃·타자별 안타/홈런/타점) = 박스스코어 정확 일치."""
        res = game_pair(42, True)
        pas = [e for e in res.struct_events if e["t"] == "pa"]
        # 득점 합
        runs = {"초": 0, "말": 0}
        for e in pas:
            runs[e["half"]] += len(e["scored"])
        self.assertEqual((runs["초"], runs["말"]), res.score)
        # 타자별 안타/홈런/타점
        h, hr, rbi = Counter(), Counter(), Counter()
        for e in pas:
            pid = e["batter"]["pid"]
            if e["outcome"] in ("1B", "2B", "3B", "HR"):
                h[pid] += 1
            if e["outcome"] == "HR":
                hr[pid] += 1
            rbi[pid] += e["rbi"]
        for s in ("away", "home"):
            for p, _slot, bl in res.box_bat[s]:
                self.assertEqual(h[p.pid], bl.h, f"{p.name} 안타 불일치")
                self.assertEqual(hr[p.pid], bl.hr, f"{p.name} 홈런 불일치")
                self.assertEqual(rbi[p.pid], bl.rbi, f"{p.name} 타점 불일치")
        # 종료 이벤트 스코어
        end = res.struct_events[-1]
        self.assertEqual(end["t"], "game_end")
        self.assertEqual(tuple(end["score"]), res.score)

    def test_stream_reproducible(self):
        """같은 시드 → 같은 스트림 (관전 내용 재현)."""
        e1 = game_pair(7, True).struct_events
        e2 = game_pair(7, True).struct_events
        self.assertEqual(e1, e2)

    def test_count_seq_consistent_with_outcome(self):
        """볼카운트 연출이 결과와 정합 (K는 S로, BB는 B 4개, 인플레이는 X로 끝)."""
        from web.backend.serializers import watch_stream
        res = game_pair(42, True)
        stream = watch_stream(res)
        for e in stream["events"]:
            if e["t"] != "pa":
                continue
            seq = e["count_seq"]
            self.assertEqual(len(seq), max(1, e["pitches"]))
            if e["outcome"] == "K":
                self.assertEqual(seq[-1], "S")
                self.assertEqual(sum(1 for x in seq if x == "B") <= 3, True)
            elif e["outcome"] == "BB":
                self.assertEqual(seq[-1], "B")
                self.assertEqual(sum(1 for x in seq if x == "B"), 4)
            elif e["outcome"] == "HBP":
                self.assertEqual(seq[-1], "H")
            else:
                self.assertEqual(seq[-1], "X")


if __name__ == "__main__":
    unittest.main()
