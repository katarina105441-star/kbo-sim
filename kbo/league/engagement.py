"""시즌 중 구단주 이벤트·목표 보상·업적 시스템.

이벤트 선택은 경기 RNG를 사용하지 않는다. 연도·구단·시점으로 결정되는 고정
이벤트가 예산, 구단주 신뢰도, 프런트 포인트에만 영향을 준다.
"""
from __future__ import annotations

from dataclasses import asdict

from ..engine.probability import clamp
from .front_office import ensure_front_office, visible_rank
from .team_identity import identity_of

EVENT_MILESTONES = (24, 72, 120)

ACHIEVEMENTS = {
    "boardroom_debut": {
        "title": "첫 이사회", "description": "구단주 이벤트에 처음 응답", "reward": 2.0,
    },
    "first_objective": {
        "title": "약속 이행", "description": "시즌 목표 첫 달성", "reward": 4.0,
    },
    "champion": {
        "title": "정상 정복", "description": "한국시리즈 첫 우승", "reward": 10.0,
    },
    "trusted_manager": {
        "title": "구단주의 신임", "description": "구단주 신뢰도 80 이상", "reward": 4.0,
    },
    "turnaround": {
        "title": "반등", "description": "목표 실패 다음 시즌에 목표 달성", "reward": 5.0,
    },
    "five_seasons": {
        "title": "장기 집권", "description": "한 구단에서 5시즌 평가 완료", "reward": 6.0,
    },
    "dynasty": {
        "title": "왕조", "description": "한국시리즈 3회 우승", "reward": 15.0,
    },
    "front_office_ace": {
        "title": "프런트의 달인", "description": "프런트 포인트 10 획득", "reward": 5.0,
    },
}


def ensure_engagement(session) -> None:
    ensure_front_office(session)
    defaults = (
        ("pending_owner_event", None),
        ("issued_owner_events", set()),
        ("owner_event_history", []),
        ("front_office_points", 0),
        ("achievements", {}),
        ("rewarded_seasons", set()),
    )
    for name, value in defaults:
        if not hasattr(session, name):
            setattr(session, name, value.copy() if hasattr(value, "copy") else value)
    if not isinstance(session.issued_owner_events, set):
        session.issued_owner_events = set(session.issued_owner_events)
    if not isinstance(session.rewarded_seasons, set):
        session.rewarded_seasons = set(session.rewarded_seasons)


def _choice(choice_id: str, label: str, description: str,
            budget: float = 0.0, confidence: float = 0.0, points: int = 0) -> dict:
    return {
        "id": choice_id,
        "label": label,
        "description": description,
        "effects": {"budget": budget, "confidence": confidence, "points": points},
    }


def _build_event(session, milestone: int) -> dict:
    identity = identity_of(session.user_team)
    target = session.current_objective.target_rank
    rank = visible_rank(session)

    if milestone == 24:
        if identity.strategy == "win_now":
            title, text = "초반 승부수 요구", "구단주가 즉시전력 보강과 빠른 성과를 요구합니다."
        elif identity.strategy == "rebuild":
            title, text = "육성 계획 보고", "구단주가 유망주 육성과 순위 회복 계획을 요구합니다."
        else:
            title, text = "시즌 운영 방향 점검", "구단주가 성적과 장기 운영의 우선순위를 묻습니다."
        choices = [
            _choice("results", "성적에 투자", "추가 운영비를 확보하는 대신 성과 약속을 강화합니다.",
                    budget=6.0, confidence=2.0, points=1),
            _choice("development", "장기 계획 유지", "운영비를 육성 기반에 투입해 프런트 역량을 쌓습니다.",
                    budget=-4.0, confidence=1.0, points=2),
        ]
    elif milestone == 72:
        if rank <= target:
            title, text = "중간 평가: 목표권", f"현재 {rank}위로 목표 {target}위 이내를 지키고 있습니다."
            choices = [
                _choice("double_down", "목표를 상향", "추가 투자를 승인하고 높은 성과를 약속합니다.",
                        budget=-5.0, confidence=4.0, points=2),
                _choice("stay_course", "계획대로 진행", "현재 운영 기조를 유지합니다.",
                        confidence=1.0, points=1),
            ]
        else:
            title, text = "중간 평가: 성적 압박", f"현재 {rank}위로 목표 {target}위보다 뒤처져 있습니다."
            choices = [
                _choice("reinforce", "긴급 예산 요청", "구단주 지원을 받지만 결과 책임이 커집니다.",
                        budget=8.0, confidence=-1.0, points=1),
                _choice("internal_fix", "내부 반등 선언", "추가 예산 없이 운영 개선을 약속합니다.",
                        confidence=-3.0, points=2),
            ]
    else:
        title, text = "시즌 막판 구단주 지시", f"최종 목표 {target}위 이내 달성을 위한 결단이 필요합니다."
        choices = [
            _choice("all_in", "막판 총력전", "운영 예산을 투입하고 구단주의 지지를 확보합니다.",
                    budget=-6.0, confidence=5.0, points=2),
            _choice("protect_future", "장기 자산 보호", "미래 전력을 지키지만 단기 기대치는 낮아집니다.",
                    confidence=-2.0, points=1),
        ]

    return {
        "id": f"{session.year}:{milestone}",
        "year": session.year,
        "day": int(session.season.day),
        "milestone": milestone,
        "title": title,
        "description": text,
        "choices": choices,
    }


def next_unissued_milestone(session) -> int | None:
    ensure_engagement(session)
    current = int(session.season.day)
    total = len(session.season.schedule)
    for milestone in EVENT_MILESTONES:
        key = f"{session.year}:{milestone}"
        if current < milestone < total and key not in session.issued_owner_events:
            return milestone
    return None


def maybe_issue_event(session) -> dict | None:
    ensure_engagement(session)
    if session.pending_owner_event is not None or session.season.finished:
        return session.pending_owner_event
    current = int(session.season.day)
    due = [m for m in EVENT_MILESTONES
           if current >= m and f"{session.year}:{m}" not in session.issued_owner_events]
    if not due:
        return None
    # 과거 저장 파일이나 큰 단위 진행으로 여러 시점을 넘긴 경우 최신 이벤트만 제시한다.
    milestone = max(due)
    for skipped in due:
        session.issued_owner_events.add(f"{session.year}:{skipped}")
    session.pending_owner_event = _build_event(session, milestone)
    return session.pending_owner_event


def _achievement_condition(session, achievement_id: str) -> bool:
    history = session.front_office_history
    events = session.owner_event_history
    if achievement_id == "boardroom_debut":
        return bool(events)
    if achievement_id == "first_objective":
        return any(row.get("goal_met") for row in history)
    if achievement_id == "champion":
        return any(row.get("champion") for row in history)
    if achievement_id == "trusted_manager":
        return session.owner_confidence >= 80
    if achievement_id == "turnaround":
        return any(not before.get("goal_met") and after.get("goal_met")
                   for before, after in zip(history, history[1:]))
    if achievement_id == "five_seasons":
        return len(history) >= 5
    if achievement_id == "dynasty":
        return sum(1 for row in history if row.get("champion")) >= 3
    if achievement_id == "front_office_ace":
        return session.front_office_points >= 10
    return False


def unlock_achievements(session) -> list[dict]:
    ensure_engagement(session)
    unlocked = []
    for achievement_id, definition in ACHIEVEMENTS.items():
        if achievement_id in session.achievements:
            continue
        if not _achievement_condition(session, achievement_id):
            continue
        row = {
            "id": achievement_id,
            "title": definition["title"],
            "description": definition["description"],
            "reward": definition["reward"],
            "year": session.year,
            "day": int(session.season.day),
        }
        session.achievements[achievement_id] = row
        session.user_team.budget = round(session.user_team.budget + definition["reward"], 2)
        unlocked.append(row)
    return unlocked


def resolve_owner_event(session, choice_id: str) -> dict:
    ensure_engagement(session)
    event = session.pending_owner_event
    if event is None:
        raise LookupError("응답할 구단주 이벤트가 없습니다.")
    choice = next((item for item in event["choices"] if item["id"] == choice_id), None)
    if choice is None:
        raise ValueError("선택할 수 없는 구단주 이벤트 응답입니다.")
    effects = choice["effects"]
    session.user_team.budget = round(session.user_team.budget + effects["budget"], 2)
    session.owner_confidence = clamp(session.owner_confidence + effects["confidence"], 0.0, 100.0)
    session.front_office_points += effects["points"]
    result = {
        "year": event["year"], "day": event["day"], "event_id": event["id"],
        "title": event["title"], "choice_id": choice["id"],
        "choice": choice["label"], "effects": dict(effects),
    }
    session.owner_event_history.append(result)
    session.pending_owner_event = None
    result["unlocked"] = unlock_achievements(session)
    return result


def apply_season_rewards(session) -> dict | None:
    ensure_engagement(session)
    if not session.front_office_history:
        return None
    result = session.front_office_history[-1]
    year = int(result["year"])
    if year in session.rewarded_seasons:
        return result
    reward = 0.0
    points = 0
    if result.get("goal_met"):
        margin = max(0, result["target_rank"] - result["actual_rank"])
        reward += 5.0 + margin * 2.0
        points += 2
    if result.get("champion"):
        reward += 15.0
        points += 3
    session.user_team.budget = round(session.user_team.budget + reward, 2)
    session.front_office_points += points
    session.rewarded_seasons.add(year)
    result["reward_budget"] = round(reward, 2)
    result["reward_points"] = points
    result["unlocked"] = unlock_achievements(session)
    return result


def achievements_payload(session) -> list[dict]:
    ensure_engagement(session)
    rows = []
    for achievement_id, definition in ACHIEVEMENTS.items():
        unlocked = session.achievements.get(achievement_id)
        rows.append({
            "id": achievement_id,
            "title": definition["title"],
            "description": definition["description"],
            "reward": definition["reward"],
            "unlocked": unlocked is not None,
            "year": unlocked.get("year") if unlocked else None,
        })
    return rows


def engagement_payload(session) -> dict:
    ensure_engagement(session)
    maybe_issue_event(session)
    achievements = achievements_payload(session)
    latest_reward = session.front_office_history[-1] if session.front_office_history else None
    return {
        "pending_event": session.pending_owner_event,
        "front_office_points": session.front_office_points,
        "event_history": list(reversed(session.owner_event_history[-8:])),
        "achievements": achievements,
        "achievement_count": sum(1 for row in achievements if row["unlocked"]),
        "achievement_total": len(achievements),
        "latest_season_reward": latest_reward,
    }
