"""감독 은퇴·명예의 전당·커리어 최종 결산.

은퇴 평가는 경기 RNG를 사용하지 않고 누적 시즌 평가와 커리어 기록만 사용한다.
10시즌부터 자발적 은퇴가 가능하며 30시즌 종료 시 자동 은퇴한다.
"""
from __future__ import annotations

import re
from statistics import mean

from ..engine.probability import clamp
from .manager_career import ensure_manager_career

VOLUNTARY_RETIREMENT_SEASONS = 10
MANDATORY_RETIREMENT_SEASONS = 30

LEGACY_TIERS = (
    (170, "legend", "KBO 감독 전설"),
    (115, "hall_of_fame", "명예의 전당"),
    (80, "master", "명장"),
    (50, "veteran", "베테랑 감독"),
    (0, "career", "프로 감독"),
)

_RECORD_RE = re.compile(r"(?P<w>\d+)승\s*(?P<t>\d+)무\s*(?P<l>\d+)패")


def ensure_career_legacy(session) -> None:
    ensure_manager_career(session)
    defaults = (
        ("retirement_summary", None),
        ("hall_of_fame", None),
        ("retirement_year", None),
        ("retirement_reason", None),
    )
    for name, value in defaults:
        if not hasattr(session, name):
            setattr(session, name, value)


def _record_totals(history: list[dict]) -> dict:
    wins = ties = losses = 0
    for row in history:
        match = _RECORD_RE.search(str(row.get("record", "")))
        if not match:
            continue
        wins += int(match.group("w"))
        ties += int(match.group("t"))
        losses += int(match.group("l"))
    return {"wins": wins, "ties": ties, "losses": losses}


def career_totals(session) -> dict:
    ensure_career_legacy(session)
    history = list(session.front_office_history)
    ranks = [int(row["actual_rank"]) for row in history if "actual_rank" in row]
    grades = {grade: sum(1 for row in history if row.get("grade") == grade)
              for grade in "SABCDF"}
    goals = sum(1 for row in history if row.get("goal_met"))
    titles = sum(1 for row in history if row.get("champion"))
    dismissals = sum(1 for row in history if row.get("dismissed"))
    teams = []
    for tenure in session.manager_tenures:
        tid = tenure.get("tid")
        if tid and tid not in teams:
            teams.append(tid)
    record = _record_totals(history)
    games = record["wins"] + record["ties"] + record["losses"]
    return {
        "seasons": len(history),
        "goals_met": goals,
        "goal_rate": round(goals / len(history), 3) if history else 0.0,
        "championships": titles,
        "best_rank": min(ranks) if ranks else None,
        "average_rank": round(mean(ranks), 2) if ranks else None,
        "grades": grades,
        "dismissals": dismissals,
        "teams_managed": teams,
        "team_count": len(teams),
        "moves": len(session.career_moves),
        "record": record,
        "games": games,
        "win_rate": round(record["wins"] / (record["wins"] + record["losses"]), 3)
                    if record["wins"] + record["losses"] else 0.0,
    }


def legacy_score(session) -> float:
    totals = career_totals(session)
    best_bonus = max(0, 8 - (totals["best_rank"] or 10)) * 1.5
    score = (
        totals["seasons"] * 1.2
        + totals["goals_met"] * 2.5
        + totals["championships"] * 22.0
        + totals["grades"]["S"] * 5.0
        + totals["grades"]["A"] * 3.0
        + totals["team_count"] * 1.5
        + best_bonus
        + max(0.0, float(session.manager_reputation) - 40.0) * 0.2
        - totals["dismissals"] * 6.0
    )
    return round(clamp(score, 0.0, 250.0), 1)


def legacy_tier(score: float) -> dict:
    for threshold, key, label in LEGACY_TIERS:
        if score >= threshold:
            return {"key": key, "label": label, "threshold": threshold}
    return {"key": "career", "label": "프로 감독", "threshold": 0}


def retirement_eligible(session) -> bool:
    ensure_career_legacy(session)
    return (session.career_status in {"employed", "dismissed"}
            and len(session.front_office_history) >= VOLUNTARY_RETIREMENT_SEASONS)


def _legacy_highlights(totals: dict) -> list[str]:
    highlights = []
    if totals["championships"]:
        highlights.append(f"한국시리즈 우승 {totals['championships']}회")
    if totals["goals_met"]:
        highlights.append(
            f"시즌 목표 {totals['goals_met']}회 달성 ({totals['goal_rate']:.0%})")
    if totals["best_rank"] is not None:
        highlights.append(
            f"정규시즌 최고 {totals['best_rank']}위·평균 {totals['average_rank']}위")
    if totals["team_count"] > 1:
        highlights.append(f"{totals['team_count']}개 구단 지휘")
    if totals["grades"]["S"] + totals["grades"]["A"]:
        highlights.append(
            f"최상위 평가 S {totals['grades']['S']}회·A {totals['grades']['A']}회")
    return highlights or ["프로 무대에서 감독 커리어 완주"]


def build_retirement_summary(session, reason: str) -> dict:
    totals = career_totals(session)
    score = legacy_score(session)
    tier = legacy_tier(score)
    inducted = tier["key"] in {"hall_of_fame", "legend"}
    return {
        "year": int(session.year),
        "reason": reason,
        "reason_label": "30시즌 임기 완주" if reason == "mandatory" else "자발적 은퇴",
        "score": score,
        "tier": tier,
        "inducted": inducted,
        "totals": totals,
        "highlights": _legacy_highlights(totals),
        "final_reputation": round(float(session.manager_reputation), 1),
        "final_team": {"tid": session.user_tid, "name": session.user_team.name},
    }


def retire_manager(session, reason: str = "voluntary", force: bool = False) -> dict:
    ensure_career_legacy(session)
    if session.career_status == "retired":
        raise LookupError("이미 은퇴한 감독입니다.")
    if not force and not retirement_eligible(session):
        raise ValueError(
            f"자발적 은퇴는 {VOLUNTARY_RETIREMENT_SEASONS}시즌을 마친 뒤 가능합니다.")

    if session.manager_tenures and session.manager_tenures[-1].get("end_year") is None:
        session.manager_tenures[-1]["end_year"] = int(session.year)
        session.manager_tenures[-1]["exit_reason"] = (
            "30시즌 임기 완주" if reason == "mandatory" else "자발적 은퇴")
    for team in session.teams:
        team.user_managed = False
    for attr in ("trade_session", "fa_session", "draft_session"):
        if hasattr(session, attr):
            setattr(session, attr, None)
    session.job_offers = []
    session.career_status = "retired"
    session.retirement_year = int(session.year)
    session.retirement_reason = reason
    session.retirement_summary = build_retirement_summary(session, reason)
    session.hall_of_fame = {
        "inducted": session.retirement_summary["inducted"],
        "score": session.retirement_summary["score"],
        "tier": session.retirement_summary["tier"],
        "year": int(session.year),
    }
    session.media_feed.append({
        "year": int(session.year),
        "team": session.user_team.name,
        "headline": (
            f"감독, {session.retirement_summary['reason_label']} 선언…"
            f"최종 평가 {session.retirement_summary['tier']['label']}"
        ),
        "tone": "positive",
    })
    return session.retirement_summary


def maybe_auto_retire(session) -> dict | None:
    ensure_career_legacy(session)
    if session.career_status == "retired":
        return session.retirement_summary
    if len(session.front_office_history) >= MANDATORY_RETIREMENT_SEASONS:
        return retire_manager(session, reason="mandatory", force=True)
    return None


def career_legacy_payload(session) -> dict:
    ensure_career_legacy(session)
    totals = career_totals(session)
    score = legacy_score(session)
    return {
        "retirement_eligible": retirement_eligible(session),
        "retirement_min_seasons": VOLUNTARY_RETIREMENT_SEASONS,
        "retirement_mandatory_seasons": MANDATORY_RETIREMENT_SEASONS,
        "legacy_preview": {
            "score": score,
            "tier": legacy_tier(score),
            "totals": totals,
        },
        "retirement_summary": session.retirement_summary,
        "hall_of_fame": session.hall_of_fame,
    }


def balance_assessment(careers: list[dict]) -> dict:
    """여러 장기 커리어 결과의 과도한 해임·우승·명예의 전당 편중을 점검한다."""
    if not careers:
        return {"sample_size": 0, "checks": [], "passed": False}
    n = len(careers)
    avg_dismissals = mean(row.get("dismissals", 0) for row in careers)
    avg_titles = mean(row.get("championships", 0) for row in careers)
    avg_teams = mean(row.get("team_count", 1) for row in careers)
    hof_rate = sum(1 for row in careers if row.get("inducted")) / n
    checks = [
        {"name": "평균 해임 횟수", "value": round(avg_dismissals, 2),
         "minimum": 0.2, "maximum": 8.0, "passed": 0.2 <= avg_dismissals <= 8.0},
        {"name": "평균 우승 횟수", "value": round(avg_titles, 2),
         "minimum": 0.0, "maximum": 10.0, "passed": 0.0 <= avg_titles <= 10.0},
        {"name": "평균 지휘 구단 수", "value": round(avg_teams, 2),
         "minimum": 1.0, "maximum": 6.0, "passed": 1.0 <= avg_teams <= 6.0},
        {"name": "명예의 전당 비율", "value": round(hof_rate, 3),
         "minimum": 0.0, "maximum": 0.65, "passed": hof_rate <= 0.65},
    ]
    return {
        "sample_size": n,
        "average_dismissals": round(avg_dismissals, 2),
        "average_championships": round(avg_titles, 2),
        "average_teams": round(avg_teams, 2),
        "hall_of_fame_rate": round(hof_rate, 3),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }
