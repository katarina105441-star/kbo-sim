"""단일 경기 시뮬 + 박스스코어 출력.

사용법:  python scripts/play_game.py --home KIA --away LG [--seed 42] [--verbose]
팀 ID: KIA LG DSN SSG SAM KT LTE HWE NC KWM
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league, team_by_id
from kbo.io.report import boxscore_text, events_text
from kbo.engine.game import GameSimulator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="KIA")
    ap.add_argument("--away", default="LG")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--verbose", action="store_true", help="타석별 이벤트 로그 출력")
    args = ap.parse_args()

    teams = load_league()
    home, away = team_by_id(teams, args.home), team_by_id(teams, args.away)
    rng = random.Random(args.seed)
    res = GameSimulator(home, away, rng, record=False, record_events=args.verbose).run()

    print(f"=== {away.name} @ {home.name} ({home.stadium}) ===\n")
    if args.verbose:
        print(events_text(res))
        print()
    print(boxscore_text(res))


if __name__ == "__main__":
    main()
