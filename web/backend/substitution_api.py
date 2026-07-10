"""MVP-3 Part 2B 실시간 야수 교체 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()


class PinchHitterRequest(BaseModel):
    pid: str


class PinchRunnerRequest(BaseModel):
    pid: str
    base: int = Field(ge=1, le=3)


class DefensiveSubRequest(BaseModel):
    out_pid: str
    in_pid: str


def _context():
    # main 모듈 로딩이 끝난 뒤 요청 시점에만 가져와 순환 import를 피한다.
    from web.backend import main
    s = main.sess()
    try:
        sim = s.require_live()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    user_side = "home" if sim.home.tid == s.user_tid else "away"
    return main, s, sim, user_side


def _sub_text(ev: dict) -> str:
    label = {"pinch_hitter": "대타", "pinch_runner": "대주자",
             "defensive": "대수비"}.get(ev.get("kind"), "선수 교체")
    text = (f"{ev['inning']}회{ev['half']} {label}: "
            f"{ev['out']['name']} → {ev['in']['name']}")
    if ev.get("base"):
        text += f" ({ev['base']}루)"
    return text


def _payload(main, s, sim, event_from: int):
    events = [dict(ev) for ev in sim.struct_events[event_from:]]
    for ev in events:
        if ev.get("t") == "substitution":
            ev["text"] = _sub_text(ev)
    payload = main._live_payload(s)
    payload["events"] = events
    return payload


def _state_guard(sim, expected_side: str, user_side: str, action: str):
    if sim.done or not sim.at_decision:
        raise HTTPException(409, f"{action}는 다음 타석 시작 전에만 가능합니다.")
    if expected_side != user_side:
        phase = "공격" if action in ("대타", "대주자") else "수비"
        raise HTTPException(409, f"우리 팀 {phase} 중에만 {action}를 사용할 수 있습니다.")


@router.post("/api/live/pinch-hitter")
def live_pinch_hitter(req: PinchHitterRequest):
    main, s, sim, user_side = _context()
    _state_guard(sim, sim.side, user_side, "대타")
    event_from = len(sim.struct_events)
    try:
        sim.force_pinch_hitter(user_side, req.pid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _payload(main, s, sim, event_from)


@router.post("/api/live/pinch-runner")
def live_pinch_runner(req: PinchRunnerRequest):
    main, s, sim, user_side = _context()
    _state_guard(sim, sim.side, user_side, "대주자")
    event_from = len(sim.struct_events)
    try:
        sim.force_pinch_runner(user_side, req.base, req.pid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _payload(main, s, sim, event_from)


@router.post("/api/live/defense")
def live_defensive_sub(req: DefensiveSubRequest):
    main, s, sim, user_side = _context()
    _state_guard(sim, sim.fld, user_side, "대수비")
    event_from = len(sim.struct_events)
    try:
        sim.force_defensive_sub(user_side, req.out_pid, req.in_pid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _payload(main, s, sim, event_from)
