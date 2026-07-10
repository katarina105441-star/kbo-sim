"""사용자 1군·2군 이동과 육성 방향 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kbo.league.aging import potential
from kbo.league.development import (
    ACTIVE_MAX,
    ACTIVE_MIN,
    FOCUS_OPTIONS,
    auto_assign_active,
    demote,
    promote,
    set_focus,
)
from web.backend import serializers as ser

router = APIRouter()


class PlayerMoveRequest(BaseModel):
    pid: str = Field(min_length=1)


class FocusRequest(BaseModel):
    pid: str = Field(min_length=1)
    focus: str = Field(min_length=1, max_length=20)


def _context():
    from web.backend import main
    return main, main.sess()


def _check_editable(session) -> None:
    if session.live_sim is not None and not session.live_sim.done:
        raise HTTPException(409, "실시간 경기 중에는 1군·2군을 변경할 수 없습니다.")
    if getattr(session.season, "pending_day", None) is not None:
        raise HTTPException(409, "진행 중인 경기일에는 1군·2군을 변경할 수 없습니다.")


def _player_payload(player, level: str) -> dict:
    data = ser.player_brief(player)
    data.update({
        "level": level,
        "pot": round(potential(player), 1),
        "focus": player.development_focus,
        "minor_days": player.minor_days,
        "minor_seasons": player.minor_seasons,
        "dev_last_gain": player.dev_last_gain,
    })
    return data


def development_state(session=None) -> dict:
    if session is None:
        _main, session = _context()
    team = session.user_team
    active = sorted(team.roster, key=lambda p: (p.is_pitcher, -p.pit_overall if p.is_pitcher else -p.bat_overall))
    minors = sorted(team.minors, key=lambda p: (p.is_pitcher, -p.pit_overall if p.is_pitcher else -p.bat_overall))
    return {
        "team": {"tid": team.tid, "name": team.name},
        "active_count": len(active),
        "minor_count": len(minors),
        "active_min": ACTIVE_MIN,
        "active_max": ACTIVE_MAX,
        "focus_options": sorted(FOCUS_OPTIONS),
        "active": [_player_payload(p, "active") for p in active],
        "minors": [_player_payload(p, "minors") for p in minors],
    }


def _run(action):
    main, session = _context()
    _check_editable(session)
    try:
        result = action(session.user_team)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "result": result,
        "development": development_state(session),
        "game_state": main.game_state(),
    }


@router.get("/api/development/state")
def state():
    _main, session = _context()
    return development_state(session)


@router.post("/api/development/promote")
def promote_player(req: PlayerMoveRequest):
    return _run(lambda team: {
        "action": "promote",
        "player": _player_payload(promote(team, req.pid), "active"),
    })


@router.post("/api/development/demote")
def demote_player(req: PlayerMoveRequest):
    return _run(lambda team: {
        "action": "demote",
        "player": _player_payload(demote(team, req.pid), "minors"),
    })


@router.put("/api/development/focus")
def update_focus(req: FocusRequest):
    return _run(lambda team: {
        "action": "focus",
        "player": _player_payload(set_focus(team, req.pid, req.focus), "minors"),
    })


@router.post("/api/development/auto")
def auto_roster():
    return _run(lambda team: {
        "action": "auto",
        **auto_assign_active(team),
    })
