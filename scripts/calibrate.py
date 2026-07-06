"""밸런싱 하네스 — N시즌 시뮬 → 리그 지표를 실제 KBO 목표 범위와 비교.

사용법:  python scripts/calibrate.py [--seasons 20] [--seed 1]
TUNE 상수(kbo/engine/probability.py)를 수정하며 반복 실행한다.
"""
import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.season import SeasonRunner

# 목표 범위 (DESIGN.md 5절)
TARGETS = {
    "타율":        (0.260, 0.275),
    "출루율":      (0.335, 0.350),
    "장타율":      (0.385, 0.410),
    "ERA":         (4.20, 4.80),
    "득점/경기":   (4.60, 5.20),
    "홈런/경기":   (0.75, 1.00),
    "K/9":         (7.00, 8.00),
    "BB/9":        (3.30, 4.00),
    "도루성공률":  (0.68, 0.75),
    "팀당병살":    (95, 120),
    "팀당실책":    (80, 120),
}


def collect(n_seasons: int, seed: int) -> dict:
    teams = load_league()
    rng = random.Random(seed)
    agg = {k: 0.0 for k in TARGETS}
    win_max, win_min = 0, 999
    best_avg, best_hr, best_era = 0.0, 0, 99.0
    for s in range(n_seasons):
        season = SeasonRunner(teams, rng)
        season.run()
        tot = season.league_totals()
        b, p = tot.bat, tot.pit
        agg["타율"] += b.avg
        agg["출루율"] += b.obp
        agg["장타율"] += b.slg
        agg["ERA"] += p.era
        agg["득점/경기"] += tot.r_per_game
        agg["홈런/경기"] += tot.hr_per_game
        agg["K/9"] += p.k9
        agg["BB/9"] += p.bb9
        agg["도루성공률"] += tot.sb_pct
        agg["팀당병살"] += b.gdp / len(teams)
        agg["팀당실책"] += b.e / len(teams)
        agg.setdefault("_비자책률", 0.0)
        agg["_비자책률"] += (p.r - p.er) / p.r if p.r else 0.0
        st = season.standings()
        win_max = max(win_max, st[0].wins)
        win_min = min(win_min, st[-1].wins)
        for t in teams:
            for pl in t.roster:
                sb = pl.season_bat
                if sb.pa >= 446 and sb.avg > best_avg:
                    best_avg = sb.avg
                if sb.hr > best_hr:
                    best_hr = sb.hr
                sp = pl.season_pit
                if sp.outs >= 432 and sp.era < best_era:
                    best_era = sp.era
    metrics = {k: v / n_seasons for k, v in agg.items() if not k.startswith("_")}
    metrics["_extremes"] = (win_max, win_min, best_avg, best_hr, best_era)
    metrics["_unearned"] = agg.get("_비자책률", 0.0) / n_seasons
    return metrics


def report(metrics: dict, label: str) -> bool:
    print(f"\n=== {label} ===")
    print(f"{'지표':<10}{'결과':>9}{'목표':>17}  판정")
    all_ok = True
    for k, (lo, hi) in TARGETS.items():
        v = metrics[k]
        ok = lo <= v <= hi
        all_ok &= ok
        fmt = ".3f" if v < 2 else (".2f" if v < 20 else ".0f")
        print(f"{k:<11}{v:>9{fmt}}{f'{lo}~{hi}':>16}  {'OK' if ok else '<<< 벗어남'}")
    wm, wn, ba, bh, be = metrics["_extremes"]
    print(f"(분포) 최다승 {wm} / 최소승 {wn} · 최고타율 {ba:.3f} · 최다HR {bh} · 최저ERA {be:.2f}"
          f" · 비자책률 {metrics['_unearned']:.1%}")
    return all_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    t0 = time.time()
    metrics = collect(args.seasons, args.seed)
    ok = report(metrics, f"{args.seasons}시즌 평균 ({time.time() - t0:.0f}초)")
    print("\n전 지표 목표 범위 내 ✔" if ok else "\nTUNE 조정 필요")


if __name__ == "__main__":
    main()
