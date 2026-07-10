"""사용자 참여 FA 시장 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class FAOfferRequest(BaseModel):
    aav: float = Field(gt=0)


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


@router.get("/api/fa/state")
def fa_state():
    _main, session = _context()
    try:
        return session.fa_state()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/fa/offer")
def fa_offer(req: FAOfferRequest):
    return _run(lambda session, aav: session.fa_offer(aav), req.aav)


@router.post("/api/fa/pass")
def fa_pass():
    return _run(lambda session: session.fa_pass())


@router.post("/api/fa/auto")
def fa_auto():
    return _run(lambda session: session.fa_auto())


@router.post("/api/fa/auto-finish")
def fa_auto_finish():
    return _run(lambda session: session.fa_auto_finish())
