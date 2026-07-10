"""시즌 목표·구단주 신뢰도·장기 성과 API."""
from __future__ import annotations

from fastapi import APIRouter

from kbo.league.front_office import front_office_payload

router = APIRouter()


@router.get("/api/front-office")
def front_office_state():
    from web.backend.main import sess
    return front_office_payload(sess())
