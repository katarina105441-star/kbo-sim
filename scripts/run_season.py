"""풀시즌 파이프라인 — 정규시즌 144경기 → 순위 확정 → 포스트시즌 → 최종 우승팀.

사용법:  python scripts/run_season.py [--seed 42] [--no-ps]
"""
import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.io.report import (standings_text, league_report_text, leaders_text,
                           postseason_text, ps_leaders_text)
from kbo.league.season import SeasonRunner
from kbo.league.postseason import PostseasonRunner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-ps", action="store_true", help="정규시즌만 시뮬")
    args = ap.parse_args()

    teams = load_league()
    rng = random.Random(args.seed)
    season = SeasonRunner(teams, rng)
    t0 = time.time()
    season.run()
    dt = time.time() - t0

    print(f"=== 정규시즌 결과 (720경기, {dt:.1f}초) ===\n")
    print(standings_text(season))
    print("\n=== 리그 지표 ===")
    print(league_report_text(season.league_totals()))
    print("\n=== 개인 타이틀 ===")
    print(leaders_text(teams))

    if not args.no_ps:
        ranked = season.standings()
        ps = PostseasonRunner(ranked, rng, start_day=season.days_played).run()
        print("\n=== 포스트시즌 ===")
        print(postseason_text(ps, ranked))
        print("\n=== 포스트시즌 개인 기록 (별도 집계) ===")
        print(ps_leaders_text(teams))


if __name__ == "__main__":
    main()
