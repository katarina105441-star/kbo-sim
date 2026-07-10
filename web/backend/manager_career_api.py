"""감독 커리어·해임·재취업 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kbo.league.manager_career import accept_job_offer, manager_career_payload

router = APIRouter()


class JobAcceptRequest(BaseModel):
    tid: str


@router.get("/api/career")
def career_state():
    from web.backend.main import sess
    return manager_career_payload(sess())


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
        "career": manager_career_payload(sess()),
        "state": game_state(),
    }
