"""감독 커리어·해임·재취업·은퇴·명예의 전당 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kbo.league.career_legacy import career_legacy_payload, retire_manager
from kbo.league.manager_career import accept_job_offer, manager_career_payload

router = APIRouter()


class JobAcceptRequest(BaseModel):
    tid: str


def _career_payload(session) -> dict:
    payload = manager_career_payload(session)
    payload.update(career_legacy_payload(session))
    if session.career_status == "retired":
        summary = session.retirement_summary
        payload["current_headline"] = (
            f"커리어 종료…최종 평가 {summary['tier']['label']}·"
            f"레거시 점수 {summary['score']}"
        )
    return payload


@router.get("/api/career")
def career_state():
    from web.backend.main import sess
    return _career_payload(sess())


@router.post("/api/career/accept")
def career_accept(req: JobAcceptRequest):
    from web.backend.main import game_state, sess
    try:
        move = accept_job_offer(sess(), req.tid)
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "move": move,
        "career": _career_payload(sess()),
        "state": game_state(),
    }


@router.post("/api/career/retire")
def career_retire():
    from web.backend.main import game_state, sess
    session = sess()
    if session.live_sim is not None and not session.live_sim.done:
        raise HTTPException(409, "진행 중인 실시간 경기를 먼저 종료해야 합니다.")
    try:
        summary = retire_manager(session)
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if hasattr(session, "pending_owner_event"):
        session.pending_owner_event = None
    return {
        "summary": summary,
        "career": _career_payload(session),
        "state": game_state(),
    }
