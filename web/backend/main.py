"""FastAPI 앱 — 엔진 위 얇은 API 껍질 (표현 계층, 게임 로직 없음).

실행:  python -m uvicorn web.backend.main:app --port 8000
접속:  http://localhost:8000  (빌드된 프론트 서빙)
"""
from __future__ import annotations
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.backend import serializers as ser
from web.backend.lineup import ai_recommend, apply_lineup, lineup_payload
from web.backend.session import GameSession

app = FastAPI(title="KBO 매니저")
SESSION: GameSession | None = None
TEAM_LIST_CACHE = None


def sess() -> GameSession:
    if SESSION is None:
        raise HTTPException(404, "게임이 없습니다. 먼저 팀을 선택해 시작하세요.")
    return SESSION


class NewGame(BaseModel):
    tid: str
    seed: int | None = None


class Advance(BaseModel):
    unit: str  # day | series | month | season_end


class LineupUpdate(BaseModel):
    order: list[str] = Field(default_factory=list)
    slots: dict[str, str] = Field(default_factory=dict)
    rotation: list[str] = Field(default_factory=list)
    closer: str | None = None
    setup: list[str] = Field(default_factory=list)
    use_ai: bool = False


class LivePitcherChange(BaseModel):
    pid: str


@app.get("/api/teams/all")
def teams_all():
    """팀 선택 화면용 (게임 시작 전에도 호출 가능)."""
    global TEAM_LIST_CACHE
    if TEAM_LIST_CACHE is None:
        from kbo.io.loader import load_league
        TEAM_LIST_CACHE = [{"tid": t.tid, "name": t.name, "city": t.city,
                            "stadium": t.stadium} for t in load_league()]
    return TEAM_LIST_CACHE


@app.post("/api/game/new")
def game_new(req: NewGame):
    global SESSION
    SESSION = GameSession(req.tid, req.seed)
    return game_state()


def _visible_standings(s) -> list[dict]:
    """순위표 — 미관전 숨김 경기가 있으면 그 직전 스냅샷 기록으로 (스포일러 방지)."""
    recs = s.visible_records()
    if recs is None:
        return ser.standings_rows(s.season.standings())
    def pct(w, l):
        return w / (w + l) if (w + l) else 0.0
    ranked = sorted(s.teams, key=lambda t: (pct(recs[t.tid][0], recs[t.tid][2]),
                                            recs[t.tid][0]), reverse=True)
    top_w, _, top_l = recs[ranked[0].tid]
    rows = []
    for i, t in enumerate(ranked, 1):
        w, ti, l = recs[t.tid]
        rows.append({"tid": t.tid, "name": t.name, "city": t.city,
                     "stadium": t.stadium, "games": w + ti + l, "wins": w,
                     "ties": ti, "losses": l, "pct": round(pct(w, l), 3),
                     "budget": t.budget, "rank": i,
                     "gb": round(((top_w - w) + (l - top_l)) / 2, 1)})
    return rows


@app.get("/api/game/state")
def game_state():
    s = sess()
    season = s.season
    upcoming = []
    if not season.finished:
        for hi, ai in season.schedule[season.day]:
            h, a = s.teams[hi], s.teams[ai]
            if s.user_tid in (h.tid, a.tid):
                upcoming.append({"home": h.tid, "away": a.tid})
    rows = _visible_standings(s)
    mine = next(r for r in rows if r["tid"] == s.user_tid)
    my_team = ser.team_summary(s.user_team)
    my_team.update({k: mine[k] for k in ("games", "wins", "ties", "losses", "pct")})
    return {
        "year": s.year, "day": season.day, "days_total": len(season.schedule),
        "user_tid": s.user_tid, "my_team": my_team,
        "my_rank": mine["rank"],
        "next_games": upcoming, "news": s.current_news(),
        "history": s.history, "postseason": s.postseason_summary,
        "has_offseason_report": bool(s.offseason_reports),
        "live_active": bool(s.live_sim is not None and not s.live_sim.done),
    }


@app.post("/api/game/save")
def game_save():
    return {"path": sess().save()}


@app.post("/api/game/load")
def game_load():
    global SESSION
    try:
        SESSION = GameSession.load()
    except FileNotFoundError:
        raise HTTPException(404, "저장 파일이 없습니다.")
    return game_state()


@app.post("/api/sim/advance")
def sim_advance(req: Advance):
    if req.unit not in ("day", "series", "month", "season_end"):
        raise HTTPException(400, f"unit 오류: {req.unit}")
    try:
        out = sess().advance(req.unit)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    out["state"] = game_state()
    return out


@app.get("/api/standings")
def standings():
    return _visible_standings(sess())


@app.get("/api/teams/{tid}/roster")
def team_roster(tid: str):
    s = sess()
    t = next((x for x in s.teams if x.tid == tid.upper()), None)
    if t is None:
        raise HTTPException(404, f"팀 없음: {tid}")
    return ser.roster(t)


@app.get("/api/players/{pid}")
def player(pid: str):
    for t in sess().teams:
        for p in t.roster + getattr(t, "minors", []):
            if p.pid == pid:
                return ser.player_detail(p)
    raise HTTPException(404, f"선수 없음: {pid}")


@app.get("/api/my/lineup")
def my_lineup():
    """유저 팀의 현재 타순·수비 슬롯·투수 보직과 편집 후보를 반환."""
    return lineup_payload(sess().user_team)


@app.put("/api/my/lineup")
def my_lineup_update(req: LineupUpdate):
    """라인업 전체를 원자적으로 저장. ``use_ai``면 AI 추천으로 초기화."""
    s = sess()
    if s.live_sim is not None and not s.live_sim.done:
        raise HTTPException(409, "실시간 경기 중에는 라인업을 변경할 수 없습니다.")
    team = s.user_team
    try:
        if req.use_ai:
            return ai_recommend(team)
        return apply_lineup(team, req.order, req.slots, req.rotation,
                            req.closer, req.setup)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def _serialize_live_events(events: list[dict]) -> list[dict]:
    """관전 스트림과 동일한 표현용 필드를 실시간 이벤트에 추가한다."""
    out = []
    for ev in events:
        e = dict(ev)
        if e["t"] == "pa":
            e["count_seq"] = ser._count_seq(random.Random(e["seed"]),
                                              e["outcome"], e["pitches"])
            e["text"] = ser._pa_text(e)
        elif e["t"] == "steal":
            e["text"] = (f"{e['inning']}회{e['half']} {e['runner']['name']} "
                         f"2루 도루 {'성공' if e['success'] else '실패'}")
        elif e["t"] == "pitch_change":
            e["text"] = (f"{e['inning']}회{e['half']} {e['team']} 투수 교체: "
                         f"{e['in']['name']}")
        out.append(e)
    return out


def _live_payload(s: GameSession, out: dict | None = None) -> dict:
    try:
        sim = s.require_live()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    state = sim.state()
    user_side = "home" if sim.home.tid == s.user_tid else "away"
    payload = {
        "meta": {
            "away": {"tid": sim.away.tid, "name": sim.away.name},
            "home": {"tid": sim.home.tid, "name": sim.home.name},
            "user_side": user_side,
            "day": s.live_day_no,
            "game_idx": s.live_game_idx,
        },
        "state": state,
        "events": _serialize_live_events((out or {}).get("events", [])),
        "done": sim.done,
        "result": ser.boxscore(sim.result) if sim.done and sim.result else None,
    }
    return payload


@app.post("/api/live/start")
def live_start():
    s = sess()
    try:
        s.start_live()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _live_payload(s)


@app.get("/api/live/state")
def live_state():
    return _live_payload(sess())


@app.post("/api/live/step")
def live_step():
    s = sess()
    try:
        out = s.live_step()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _live_payload(s, out)


@app.post("/api/live/pitcher")
def live_pitcher(req: LivePitcherChange):
    s = sess()
    try:
        sim = s.require_live()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    user_side = "home" if sim.home.tid == s.user_tid else "away"
    if sim.done or not sim.at_decision or sim.fld != user_side:
        raise HTTPException(409, "현재 시점에는 투수를 교체할 수 없습니다.")
    try:
        s.live_change_pitcher(req.pid)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _live_payload(s)


@app.post("/api/live/auto")
def live_auto():
    s = sess()
    try:
        out = s.live_auto()
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _live_payload(s, out)


@app.get("/api/results")
def results(day: int | None = None):
    s = sess()
    if not s.results_by_day:
        return {"day": 0, "games": []}
    idx = (len(s.results_by_day) - 1) if day is None else day - 1
    if not 0 <= idx < len(s.results_by_day):
        raise HTTPException(404, f"일자 범위 밖: {day}")
    games = []
    for gi, r in enumerate(s.results_by_day[idx]):
        row = ser.game_row(r)
        if s.is_hidden(idx + 1, gi):     # 미관전 내 경기: 스코어 숨김
            row.update({"score": None, "tie": None, "hidden": True})
        games.append(row)
    return {"day": idx + 1, "last_day": len(s.results_by_day), "games": games}


@app.get("/api/results/{day}/{game_idx}")
def boxscore(day: int, game_idx: int):
    s = sess()
    try:
        res = s.results_by_day[day - 1][game_idx]
    except IndexError:
        raise HTTPException(404, "경기 없음")
    s.reveal(day, game_idx)             # 결과 보기 = 공개에 동의한 것
    return ser.boxscore(res)


@app.get("/api/offseason/report")
def offseason_report():
    return sess().offseason_reports


WATCH_CHUNK = 40


def _watch_res(day: int, game_idx: int):
    s = sess()
    try:
        res = s.results_by_day[day - 1][game_idx]
    except IndexError:
        raise HTTPException(404, "경기 없음")
    if not res.struct_events:
        raise HTTPException(404, "관전 불가 — 내 팀 경기만 관전할 수 있습니다.")
    return s, res


@app.get("/api/watch/{day}/{game_idx}")
def watch(day: int, game_idx: int, frm: int = 0):
    """스트림을 청크로 노출 — 재생된 시점 너머(남은 이닝·최종 결과)를 화면이
    미리 알 수 없다. 마지막 청크가 전달되면 그 경기는 공개 처리."""
    s, res = _watch_res(day, game_idx)
    stream = ser.watch_stream(res)
    evs = stream["events"]
    end = min(len(evs), frm + WATCH_CHUNK)
    done = end >= len(evs)
    meta = stream["meta"]
    if done:
        s.reveal(day, game_idx)
    else:
        meta = {k: v for k, v in meta.items() if k != "final"}   # 최종 결과 은닉
    return {"meta": meta, "events": evs[frm:end], "next": end, "done": done}


@app.post("/api/watch/{day}/{game_idx}/skip")
def watch_skip(day: int, game_idx: int, frm: int = 0):
    """결과로 건너뛰기 — 남은 스트림 전부 + 최종 결과 반환, 경기 공개."""
    s, res = _watch_res(day, game_idx)
    s.reveal(day, game_idx)
    stream = ser.watch_stream(res)
    return {"meta": stream["meta"], "events": stream["events"][frm:],
            "next": len(stream["events"]), "done": True}


# 빌드된 프론트 정적 서빙 (web/frontend/dist)
_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
