"""FA 보상선수 보호명단·선택 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class ProtectionRequest(BaseModel):
    pids: list[str] = Field(default_factory=list)


class CompensationPlayerRequest(BaseModel):
    pid: str = Field(min_length=1)


def _context():
    from web.backend import main
    return main, main.sess()


def _run(action, *args):
    main, session = _context()
    try:
        payload = action(session, *args)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload["game_state"] = main.game_state()
    return payload


@router.get("/api/fa/compensation/state")
def compensation_state():
    _main, session = _context()
    try:
        return session.compensation_state()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/fa/compensation/protect")
def compensation_protect(req: ProtectionRequest):
    return _run(lambda session, pids: session.compensation_protect(pids), req.pids)


@router.post("/api/fa/compensation/protect-auto")
def compensation_auto_protect():
    return _run(lambda session: session.compensation_auto_protect())


@router.post("/api/fa/compensation/player")
def compensation_player(req: CompensationPlayerRequest):
    return _run(lambda session, pid: session.compensation_player(pid), req.pid)


@router.post("/api/fa/compensation/cash")
def compensation_cash():
    return _run(lambda session: session.compensation_cash())


@router.post("/api/fa/compensation/auto")
def compensation_auto():
    return _run(lambda session: session.compensation_auto())


@router.post("/api/fa/compensation/auto-finish")
def compensation_auto_finish():
    return _run(lambda session: session.compensation_auto_finish())
