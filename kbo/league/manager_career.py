"""감독 해임·재취업·구단 이동·미디어/팬 반응 모델.

시즌 평가가 끝난 뒤 확정적 조건으로 고용 상태를 갱신한다. 경기 RNG는 사용하지
않으며, 재취업 제안은 리그 순위·감독 평판·구단 운영 기조로 산정한다.
"""
from __future__ import annotations

from ..engine.probability import clamp
from .front_office import create_objective, ensure_front_office, failed_streak, visible_rank
from .team_identity import identity_of

GRADE_REPUTATION = {"S": 12, "A": 7, "B": 3, "C": -2, "D": -6, "F": -10}
GRADE_FAN = {"S": 16, "A": 9, "B": 4, "C": -3, "D": -9, "F": -15}
GRADE_MEDIA = {"S": -15, "A": -8, "B": -3, "C": 5, "D": 12, "F": 20}
STRATEGY_LABELS = {"win_now": "윈나우", "balanced": "균형", "rebuild": "리빌딩"}


def ensure_manager_career(session) -> None:
    ensure_front_office(session)
    defaults = (
        ("career_status", "employed"),
        ("manager_reputation", 50.0),
        ("fan_approval", 55.0),
        ("media_pressure", 25.0),
        ("job_offers", []),
        ("career_moves", []),
        ("media_feed", []),
        ("career_processed_years", set()),
    )
    for name, value in defaults:
        if not hasattr(session, name):
            setattr(session, name, value.copy() if hasattr(value, "copy") else value)
    if not isinstance(session.career_processed_years, set):
        session.career_processed_years = set(session.career_processed_years)
    if not hasattr(session, "manager_tenures"):
        session.manager_tenures = [{
            "tid": session.user_tid,
            "team": session.user_team.name,
            "start_year": 1,
            "end_year": None,
            "exit_reason": None,
        }]
    if not session.manager_tenures:
        session.manager_tenures.append({
            "tid": session.user_tid,
            "team": session.user_team.name,
            "start_year": session.year,
            "end_year": None,
            "exit_reason": None,
        })


def _current_tenure_history(session) -> tuple[list[dict], int]:
    start_year = 1
    if session.manager_tenures:
        start_year = int(session.manager_tenures[-1].get("start_year", 1))
    history = [row for row in session.front_office_history
               if int(row.get("year", 0)) >= start_year]
    return history, start_year


def dismissal_reason(session, evaluation: dict) -> str | None:
    confidence = float(session.owner_confidence)
    tenure_history, start_year = _current_tenure_history(session)
    failures = failed_streak(tenure_history)
    tenure_seasons = max(1, int(evaluation.get("year", session.year)) - start_year + 1)

    # 신뢰도가 사실상 소진된 경우에는 보호기간과 무관하게 계약을 종료한다.
    if confidence <= 10:
        return f"구단주 신뢰도 {confidence:.0f}까지 하락"
    # 새 구단 부임 직후 두 시즌은 장기 계획을 평가할 최소 보호기간으로 둔다.
    if tenure_seasons <= 2:
        return None
    if failures >= 4 and confidence < 25:
        return f"현 구단 시즌 목표 {failures}년 연속 실패"
    if evaluation.get("grade") == "F" and failures >= 3 and confidence < 18:
        return "현 구단 연속 최하위권 성적과 프런트 평가 F"
    return None


def _offer_score(session, team, rank: int) -> float:
    identity = identity_of(team)
    reputation = float(session.manager_reputation)
    need = rank * 7.0
    rebuild_fit = 8.0 if identity.strategy == "rebuild" else 0.0
    balanced_fit = 4.0 if identity.strategy == "balanced" else 0.0
    contender_penalty = max(0.0, 62.0 - reputation) if rank <= 4 else 0.0
    return need + rebuild_fit + balanced_fit - contender_penalty


def generate_job_offers(session, former_tid: str) -> list[dict]:
    standings = list(getattr(session, "offseason_standings", None) or session.season.standings())
    rank_map = {team.tid: index for index, team in enumerate(standings, 1)}
    candidates = [team for team in session.teams if team.tid != former_tid]
    candidates.sort(
        key=lambda team: (_offer_score(session, team, rank_map.get(team.tid, 10)), team.tid),
        reverse=True,
    )
    reputation = float(session.manager_reputation)
    count = 4 if reputation >= 75 else 3
    offers = []
    for team in candidates[:count]:
        rank = rank_map.get(team.tid, 10)
        identity = identity_of(team)
        strategy_label = STRATEGY_LABELS[identity.strategy]
        confidence = clamp(
            58.0 + reputation * 0.18 + max(0, rank - 5) * 1.5,
            55.0, 78.0,
        )
        contract_years = 3 if reputation >= 65 or rank >= 7 else 2
        offers.append({
            "tid": team.tid,
            "team": team.name,
            "city": team.city,
            "previous_rank": rank,
            "strategy": identity.strategy,
            "strategy_label": strategy_label,
            "manager_style": identity.manager_style,
            "initial_confidence": round(confidence, 1),
            "contract_years": contract_years,
            "pitch": (
                f"지난 시즌 {rank}위. {strategy_label} 기조에서 "
                f"{contract_years}년 운영 계획을 제안합니다."
            ),
        })
    return offers


def _season_headline(session, evaluation: dict) -> str:
    team = session.user_team.name
    grade = evaluation.get("grade", "C")
    if evaluation.get("champion"):
        return f"{team}, 한국시리즈 정상…감독 지도력에 찬사"
    if evaluation.get("goal_met"):
        return f"{team}, 시즌 목표 달성…프런트와 팬 신뢰 상승"
    if grade in {"D", "F"}:
        return f"{team} 부진 장기화…감독 거취 질문 커져"
    return f"{team}, 목표 미달…다음 시즌 반등 압박"


def process_season_career(session) -> dict | None:
    ensure_manager_career(session)
    if not session.front_office_history:
        return None
    evaluation = session.front_office_history[-1]
    year = int(evaluation["year"])
    if year in session.career_processed_years:
        return evaluation

    grade = evaluation.get("grade", "C")
    session.manager_reputation = clamp(
        session.manager_reputation + GRADE_REPUTATION.get(grade, 0), 0.0, 100.0)
    session.fan_approval = clamp(
        session.fan_approval + GRADE_FAN.get(grade, 0), 0.0, 100.0)
    session.media_pressure = clamp(
        session.media_pressure + GRADE_MEDIA.get(grade, 0), 0.0, 100.0)
    headline = _season_headline(session, evaluation)
    session.media_feed.append({
        "year": year,
        "team": session.user_team.name,
        "headline": headline,
        "tone": "positive" if evaluation.get("goal_met") else "negative",
    })

    reason = dismissal_reason(session, evaluation)
    if reason is not None:
        former_tid = session.user_tid
        former_team = session.user_team
        session.career_status = "dismissed"
        former_team.user_managed = False
        if session.manager_tenures and session.manager_tenures[-1].get("end_year") is None:
            session.manager_tenures[-1]["end_year"] = year
            session.manager_tenures[-1]["exit_reason"] = reason
        session.job_offers = generate_job_offers(session, former_tid)
        session.media_feed.append({
            "year": year,
            "team": former_team.name,
            "headline": f"{former_team.name}, 감독 해임 발표…사유는 {reason}",
            "tone": "critical",
        })
        for attr in ("trade_session", "fa_session", "draft_session"):
            if hasattr(session, attr):
                setattr(session, attr, None)
        evaluation["dismissed"] = True
        evaluation["dismissal_reason"] = reason
    else:
        evaluation["dismissed"] = False

    session.career_processed_years.add(year)
    return evaluation


def accept_job_offer(session, tid: str) -> dict:
    ensure_manager_career(session)
    if session.career_status != "dismissed":
        raise LookupError("현재 재취업 절차가 진행 중이 아닙니다.")
    offer = next((row for row in session.job_offers if row["tid"] == tid.upper()), None)
    if offer is None:
        raise ValueError("선택할 수 없는 구단 제안입니다.")

    old_tid = session.user_tid
    old_team = session.user_team
    new_team = next(team for team in session.teams if team.tid == offer["tid"])
    old_team.user_managed = False
    new_team.user_managed = True
    session.user_tid = new_team.tid
    session.user_team = new_team
    session.owner_confidence = float(offer["initial_confidence"])
    session.fan_approval = clamp(48.0 + session.manager_reputation * 0.12, 48.0, 65.0)
    session.media_pressure = clamp(38.0 - session.manager_reputation * 0.15, 15.0, 38.0)
    session.career_status = "employed"
    session.job_offers = []
    session.current_objective = create_objective(session)
    new_team.build_default_lineup()
    new_team.build_default_pitching()

    move = {
        "year": session.year,
        "from_tid": old_tid,
        "from_team": old_team.name,
        "to_tid": new_team.tid,
        "to_team": new_team.name,
        "contract_years": offer["contract_years"],
        "initial_confidence": offer["initial_confidence"],
        "reason": "해임 후 재취업",
    }
    session.career_moves.append(move)
    session.manager_tenures.append({
        "tid": new_team.tid,
        "team": new_team.name,
        "start_year": session.year + 1,
        "end_year": None,
        "exit_reason": None,
    })
    session.media_feed.append({
        "year": session.year,
        "team": new_team.name,
        "headline": f"{new_team.name}, 새 감독 선임…{offer['contract_years']}년 계약",
        "tone": "neutral",
    })

    standings = getattr(session, "offseason_standings", None)
    if standings is not None:
        from kbo.league.trade_session import InteractiveTradeMarket
        session.trade_session = InteractiveTradeMarket(
            session.rng, session.teams, standings, session.year, session.user_tid)
        session.last_trade_state = None
        session.fa_session = None
        session.last_fa_state = None
        session.draft_session = None
        session.last_draft_state = None
    return move


def fan_label(value: float) -> str:
    if value >= 80:
        return "열광"
    if value >= 65:
        return "지지"
    if value >= 50:
        return "관망"
    if value >= 35:
        return "불만"
    return "퇴진 요구"


def media_label(value: float) -> str:
    if value >= 80:
        return "집중 포화"
    if value >= 60:
        return "고강도 압박"
    if value >= 40:
        return "비판적"
    if value >= 20:
        return "보통"
    return "우호적"


def manager_career_payload(session) -> dict:
    ensure_manager_career(session)
    rank = visible_rank(session)
    target = session.current_objective.target_rank
    live_fan = clamp(session.fan_approval + (target - rank) * 2.5, 0.0, 100.0)
    live_media = clamp(session.media_pressure + (rank - target) * 4.0, 0.0, 100.0)
    if session.career_status == "dismissed":
        current_headline = "차기 행선지는 어디인가…복수 구단이 면접 제안"
    elif rank <= target:
        current_headline = f"{session.user_team.name}, 목표권 순항…팬 지지 확대"
    else:
        current_headline = f"{session.user_team.name}, {rank}위 부진…감독 전술 도마"
    return {
        "status": session.career_status,
        "team": {"tid": session.user_tid, "name": session.user_team.name},
        "reputation": round(float(session.manager_reputation), 1),
        "fan_approval": round(live_fan, 1),
        "fan_label": fan_label(live_fan),
        "media_pressure": round(live_media, 1),
        "media_label": media_label(live_media),
        "current_headline": current_headline,
        "job_offers": list(session.job_offers),
        "moves": list(reversed(session.career_moves[-8:])),
        "tenures": list(session.manager_tenures),
        "media_feed": list(reversed(session.media_feed[-10:])),
    }
