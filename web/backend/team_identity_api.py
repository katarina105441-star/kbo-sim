"""게임 시작 전·후 구단 성향 조회 API."""
from __future__ import annotations

from fastapi import APIRouter

from kbo.io.loader import load_league
from kbo.league.team_identity import ensure_team_identities, identity_payload

router = APIRouter()


@router.get("/api/teams/identities")
def team_identities():
    teams = load_league()
    ensure_team_identities(teams)
    return {team.tid: identity_payload(team) for team in teams}
