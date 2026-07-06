"""포스트시즌 검증 — N번의 풀시즌(정규+PS)을 돌려 아래를 확인:

1. 우승팀의 정규시즌 시드 분포 — 1위 우승률이 실제 KBO 수준(~50-60%)인지
2. 5위(와일드카드)의 한국시리즈 진출/우승 '언더독 런' 빈도
3. 단기전 혹사 영향 — 중3일 선발 경기 승률 vs 충분휴식, 연투 불펜 투입 비율

사용법:  python scripts/ps_check.py [--seasons 200] [--seed 3]
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.season import SeasonRunner
from kbo.league.postseason import PostseasonRunner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=200)
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    teams = load_league()
    rng = random.Random(args.seed)
    seed_wins = {i: 0 for i in range(1, 6)}
    ks_seed_counts = {i: 0 for i in range(1, 6)}  # KS 진출(도전자 포함) 시드 분포
    underdog_ks = 0
    agg = {"short_rest": [0, 0], "normal_rest": [0, 0],
           "relief_entries": 0, "tired_relief_entries": 0}
    total_ps_games = 0

    for s in range(args.seasons):
        season = SeasonRunner(teams, rng)
        season.run()
        ranked = season.standings()
        ps_runner = PostseasonRunner(ranked, rng, start_day=season.days_played)
        res = ps_runner.run()
        seed = {t.tid: i + 1 for i, t in enumerate(ranked)}
        seed_wins[seed[res.champion.tid]] += 1
        ks = res.rounds[-1]
        for t in (ks.upper, ks.lower):
            ks_seed_counts[seed[t.tid]] += 1
        if seed[ks.lower.tid] == 5 or seed[ks.upper.tid] == 5:
            underdog_ks += 1
        for k in ("short_rest", "normal_rest"):
            agg[k][0] += ps_runner.metrics[k][0]
            agg[k][1] += ps_runner.metrics[k][1]
        agg["relief_entries"] += ps_runner.metrics["relief_entries"]
        agg["tired_relief_entries"] += ps_runner.metrics["tired_relief_entries"]
        total_ps_games += sum(len(r.games) for r in res.rounds)

    n = args.seasons
    print(f"=== 포스트시즌 검증 ({n}시즌, seed={args.seed}) ===\n")
    print("우승팀 정규시즌 시드 분포:")
    for i in range(1, 6):
        bar = "█" * int(seed_wins[i] / n * 50)
        print(f"  {i}위  {seed_wins[i]:>4}회 ({seed_wins[i] / n:5.1%})  {bar}")
    print(f"\n한국시리즈 진출 시드 분포(도전자 포함): "
          + "  ".join(f"{i}위 {ks_seed_counts[i]}" for i in range(1, 6)))
    print(f"5위 와일드카드의 한국시리즈 진출(언더독 런): {underdog_ks}회 "
          f"({underdog_ks / n:.1%}) · 그중 우승 {seed_wins[5]}회")

    sr, nr = agg["short_rest"], agg["normal_rest"]
    print(f"\n단기전 혹사 영향 (전체 PS {total_ps_games}경기):")
    if sr[0]:
        print(f"  중3일 이하 선발 등판: {sr[0]}회 — 승률 {sr[1] / sr[0]:.3f}")
    print(f"  충분휴식(중4일+) 선발: {nr[0]}회 — 승률 {nr[1] / nr[0]:.3f}")
    print(f"  불펜 등판 중 연투 상태(입장 피로>0): "
          f"{agg['tired_relief_entries']}/{agg['relief_entries']} "
          f"({agg['tired_relief_entries'] / agg['relief_entries']:.1%})")


if __name__ == "__main__":
    main()
