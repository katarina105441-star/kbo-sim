"""감독 커리어 장기 밸런스 검증.

실제 정규시즌·포스트시즌·에이징·트레이드·FA·드래프트·재정 엔진을 사용해
복수 시드의 30시즌 감독 커리어를 자동 진행한다.

    python scripts/career_balance_check.py
    python scripts/career_balance_check.py --seeds 12 --seasons 30 --strict

검증 대상: 해임 빈도, 구단 이동 폭, 우승 편중, 명예의 전당 희소성.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick
from kbo.league.career_legacy import (
    balance_assessment,
    career_totals,
    retire_manager,
)
from kbo.league.draft import run_draft
from kbo.league.economy import init_market, offseason_finance_tick
from kbo.league.fa import run_fa_market, seed_service_years
from kbo.league.front_office import create_objective, evaluate_season
from kbo.league.manager_career import (
    accept_job_offer,
    ensure_manager_career,
    process_season_career,
)
from kbo.league.postseason import PostseasonRunner
from kbo.league.season import SeasonRunner
from kbo.league.team_identity import ensure_team_identities
from kbo.league.trade import run_trades


def new_session(seed: int):
    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    ensure_team_identities(teams)
    rng = random.Random(seed)
    user_team = teams[seed % len(teams)]
    user_team.user_managed = True
    session = SimpleNamespace(
        teams=teams,
        rng=rng,
        user_tid=user_team.tid,
        user_team=user_team,
        year=1,
        owner_confidence=65.0,
        front_office_history=[],
        current_objective=None,
        history=[],
        visible_records=lambda: None,
        offseason_standings=None,
        trade_session=None,
        fa_session=None,
        draft_session=None,
        last_trade_state=None,
        last_fa_state=None,
        last_draft_state=None,
    )
    ensure_manager_career(session)
    session.current_objective = create_objective(session)
    return session


def run_career(seed: int, seasons: int) -> dict:
    session = new_session(seed)
    dismissals = 0

    for year in range(1, seasons + 1):
        session.year = year
        session.current_objective = create_objective(session)
        session.season = SeasonRunner(session.teams, session.rng, isolated=True)
        session.season.run()
        standings = session.season.standings()
        rank = {team.tid: i for i, team in enumerate(standings, 1)}
        postseason = PostseasonRunner(
            standings, session.rng, start_day=session.season.days_played).run()
        managed_team = session.user_team
        season_row = {
            "year": year,
            "champion": postseason.champion.name,
            "my_rank": rank[managed_team.tid],
            "my_record": (
                f"{managed_team.wins}승 {managed_team.ties}무 {managed_team.losses}패"
            ),
        }
        session.history.append(season_row)
        evaluate_season(session, season_row)
        process_season_career(session)

        if session.career_status == "dismissed":
            dismissals += 1
            # 장기 자동 검증은 가장 높은 우선순위 제안을 수락한다.
            offer = session.job_offers[0]
            session.offseason_standings = None
            accept_job_offer(session, offer["tid"])

        offseason_tick(session.rng, session.teams, year=year, draft_mode=True)
        run_trades(session.rng, session.teams, standings, year=year)
        run_fa_market(session.rng, session.teams, standings, year=year)
        run_draft(session.rng, session.teams, standings, year=year)
        offseason_finance_tick(session.rng, session.teams, year=year)

    summary = retire_manager(session, reason="mandatory", force=True)
    totals = career_totals(session)
    return {
        "seed": seed,
        "dismissals": dismissals,
        "championships": totals["championships"],
        "team_count": totals["team_count"],
        "goals_met": totals["goals_met"],
        "goal_rate": totals["goal_rate"],
        "average_rank": totals["average_rank"],
        "score": summary["score"],
        "tier": summary["tier"]["label"],
        "inducted": summary["inducted"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--seasons", type=int, default=30)
    parser.add_argument("--seed-start", type=int, default=7)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    careers = [
        run_career(args.seed_start + index, args.seasons)
        for index in range(args.seeds)
    ]
    report = balance_assessment(careers)

    print(f"=== 감독 커리어 장기 검증 ({args.seeds}시드 × {args.seasons}시즌) ===\n")
    print(f"{'시드':>5} {'해임':>4} {'구단':>4} {'우승':>4} {'목표율':>7} "
          f"{'평균순위':>8} {'점수':>7}  최종 등급")
    for row in careers:
        print(
            f"{row['seed']:>5} {row['dismissals']:>4} {row['team_count']:>4} "
            f"{row['championships']:>4} {row['goal_rate']:>7.0%} "
            f"{row['average_rank']:>8.2f} {row['score']:>7.1f}  {row['tier']}"
        )

    print("\n[분포 점검]")
    for check in report["checks"]:
        verdict = "PASS" if check["passed"] else "WARN"
        print(
            f"  {verdict} {check['name']}: {check['value']} "
            f"(권장 {check['minimum']}~{check['maximum']})"
        )
    print(
        f"\n평균 해임 {report['average_dismissals']}, "
        f"평균 우승 {report['average_championships']}, "
        f"평균 지휘 구단 {report['average_teams']}, "
        f"명예의 전당 비율 {report['hall_of_fame_rate']:.0%}"
    )
    print("최종 판정:", "PASS" if report["passed"] else "조정 필요")

    if args.strict and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
