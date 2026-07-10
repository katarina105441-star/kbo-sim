"""시즌 목표·구단주 신뢰도·해임 위험·장기 성과 기록.

게임 진행 동기를 위한 프런트 평가 계층이다. 경기 결과를 바꾸지 않고 시즌 종료
순위·우승 여부만 평가해 다음 시즌 목표와 구단주 신뢰도를 갱신한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean

from ..engine.probability import clamp
from .team_identity import identity_of


@dataclass(frozen=True)
class SeasonObjective:
    year: int
    target_rank: int
    title: str
    summary: str
    strategy: str
    postseason_required: bool


RISK_LABELS = (
    (80, "절대적 신임", "secure"),
    (65, "안정", "stable"),
    (50, "관찰", "watch"),
    (35, "압박", "pressure"),
    (20, "해임 경고", "warning"),
    (0, "해임 임박", "critical"),
)


def risk_status(confidence: float) -> tuple[str, str]:
    for threshold, label, level in RISK_LABELS:
        if confidence >= threshold:
            return label, level
    return "해임 임박", "critical"


def failed_streak(history: list[dict]) -> int:
    count = 0
    for row in reversed(history):
        if row.get("goal_met"):
            break
        count += 1
    return count


def dismissal_probability(confidence: float, history: list[dict]) -> int:
    failures = failed_streak(history)
    pressure = max(0.0, 52.0 - confidence) * 1.7 + failures * 11.0
    return round(clamp(pressure, 0.0, 95.0))


def create_objective(session) -> SeasonObjective:
    identity = identity_of(session.user_team)
    base = {"win_now": 3, "balanced": 5, "rebuild": 7}[identity.strategy]
    confidence = float(getattr(session, "owner_confidence", 65.0))
    history = list(getattr(session, "front_office_history", []))

    target = base
    if confidence >= 82:
        target -= 1
    elif confidence < 35:
        target += 1
    if history and history[-1].get("actual_rank", 10) <= history[-1].get("target_rank", 10):
        target -= 1
    target = int(clamp(target, 1, 8))

    if target <= 2:
        title = "한국시리즈 진출권 경쟁"
        summary = f"정규시즌 {target}위 이내와 한국시리즈 경쟁력을 증명하십시오."
    elif target <= 5:
        title = "포스트시즌 진출"
        summary = f"정규시즌 {target}위 이내로 포스트시즌에 진출하십시오."
    else:
        title = "리빌딩 진전"
        summary = f"정규시즌 {target}위 이내로 순위 경쟁력을 회복하십시오."
    return SeasonObjective(
        year=session.year,
        target_rank=target,
        title=title,
        summary=summary,
        strategy=identity.strategy,
        postseason_required=target <= 5,
    )


def _grade(actual_rank: int, target_rank: int, champion: bool) -> str:
    if champion:
        return "S"
    margin = target_rank - actual_rank
    if margin >= 2:
        return "A"
    if margin >= 0:
        return "B"
    if margin == -1:
        return "C"
    if margin == -2:
        return "D"
    return "F"


def evaluate_season(session, season_row: dict) -> dict:
    objective = getattr(session, "current_objective", None) or create_objective(session)
    actual_rank = int(season_row["my_rank"])
    champion = season_row.get("champion") == session.user_team.name
    goal_met = actual_rank <= objective.target_rank
    grade = _grade(actual_rank, objective.target_rank, champion)

    margin = objective.target_rank - actual_rank
    delta = 6 + max(0, margin) * 2 if goal_met else -7 - abs(margin) * 3
    if champion:
        delta += 12
    elif actual_rank <= 5:
        delta += 3
    before = float(getattr(session, "owner_confidence", 65.0))
    after = clamp(before + delta, 0.0, 100.0)

    result = {
        "year": objective.year,
        "objective": objective.title,
        "target_rank": objective.target_rank,
        "actual_rank": actual_rank,
        "record": season_row.get("my_record", ""),
        "champion": champion,
        "goal_met": goal_met,
        "grade": grade,
        "confidence_before": round(before, 1),
        "confidence_after": round(after, 1),
        "confidence_delta": round(after - before, 1),
        "summary": (
            f"목표 {objective.target_rank}위 이내 달성" if goal_met
            else f"목표보다 {actual_rank - objective.target_rank}계단 낮은 순위"
        ),
    }
    session.owner_confidence = after
    session.front_office_history.append(result)
    return result


def ensure_front_office(session) -> None:
    if not hasattr(session, "owner_confidence"):
        session.owner_confidence = 65.0
    if not hasattr(session, "front_office_history"):
        session.front_office_history = []
    if not hasattr(session, "current_objective") or session.current_objective is None:
        session.current_objective = create_objective(session)


def visible_rank(session) -> int:
    records = session.visible_records()
    if records is None:
        ranked = session.season.standings()
    else:
        def pct(team):
            wins, _ties, losses = records[team.tid]
            return wins / (wins + losses) if wins + losses else 0.0
        ranked = sorted(session.teams,
                        key=lambda team: (pct(team), records[team.tid][0]),
                        reverse=True)
    return next(index for index, team in enumerate(ranked, 1)
                if team.tid == session.user_tid)


def front_office_payload(session) -> dict:
    ensure_front_office(session)
    objective = session.current_objective
    rank = visible_rank(session)
    confidence = round(float(session.owner_confidence), 1)
    risk_label, risk_level = risk_status(confidence)
    history = list(session.front_office_history)
    goal_met_count = sum(1 for row in history if row.get("goal_met"))
    ranks = [row["actual_rank"] for row in history if "actual_rank" in row]
    titles = sum(1 for row in history if row.get("champion"))
    progress = "ahead" if rank < objective.target_rank else (
        "on_track" if rank == objective.target_rank else "behind")
    return {
        "objective": asdict(objective),
        "current_rank": rank,
        "progress": progress,
        "owner_confidence": confidence,
        "risk_label": risk_label,
        "risk_level": risk_level,
        "dismissal_probability": dismissal_probability(confidence, history),
        "failed_streak": failed_streak(history),
        "latest_evaluation": history[-1] if history else None,
        "history": list(reversed(history[-8:])),
        "career": {
            "seasons": len(history),
            "goals_met": goal_met_count,
            "goal_rate": round(goal_met_count / len(history), 3) if history else 0.0,
            "best_rank": min(ranks) if ranks else None,
            "average_rank": round(mean(ranks), 2) if ranks else None,
            "championships": titles,
        },
    }
