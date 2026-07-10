"""사용자 참여 트레이드 시장 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class TradeProposalRequest(BaseModel):
    other_tid: str = Field(min_length=2, max_length=10)
    give_asset_ids: list[str] = Field(min_length=1, max_length=4)
    receive_asset_ids: list[str] = Field(min_length=1, max_length=4)


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


@router.get("/api/trade/state")
def trade_state():
    _main, session = _context()
    try:
        return session.trade_state()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/trade/propose")
def trade_propose(req: TradeProposalRequest):
    return _run(
        lambda session, tid, gives, receives:
            session.trade_propose(tid, gives, receives),
        req.other_tid, req.give_asset_ids, req.receive_asset_ids,
    )


@router.post("/api/trade/accept-counter")
def trade_accept_counter():
    return _run(lambda session: session.trade_accept_counter())


@router.post("/api/trade/reject-counter")
def trade_reject_counter():
    return _run(lambda session: session.trade_reject_counter())


@router.post("/api/trade/finish")
def trade_finish():
    return _run(lambda session: session.trade_finish())
