"""사용자 참여 신인 드래프트 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class DraftPickRequest(BaseModel):
    pid: str


def _context():
    from web.backend import main
    session = main.sess()
    return main, session


@router.get("/api/draft/state")
def draft_state():
    _main, session = _context()
    try:
        return session.draft_state()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/draft/pick")
def draft_pick(req: DraftPickRequest):
    main, session = _context()
    try:
        payload = session.draft_pick(req.pid)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload["game_state"] = main.game_state()
    return payload


@router.post("/api/draft/auto-pick")
def draft_auto_pick():
    main, session = _context()
    try:
        payload = session.draft_auto_pick()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    payload["game_state"] = main.game_state()
    return payload
