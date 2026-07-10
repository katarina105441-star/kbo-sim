"""구단주 이벤트·목표 보상·업적 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kbo.league.engagement import engagement_payload, resolve_owner_event

router = APIRouter()


class OwnerEventChoice(BaseModel):
    choice_id: str


@router.get("/api/engagement")
def engagement_state():
    from web.backend.main import sess
    return engagement_payload(sess())


@router.post("/api/engagement/choice")
def engagement_choice(req: OwnerEventChoice):
    from web.backend.main import sess
    try:
        result = resolve_owner_event(sess(), req.choice_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"result": result, "state": engagement_payload(sess())}
