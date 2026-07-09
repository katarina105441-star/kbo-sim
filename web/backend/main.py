"""FastAPI 앱 — 엔진 위 얇은 API 껍질 (표현 계층, 게임 로직 없음).

실행:  python -m uvicorn web.backend.main:app --port 8000
접속:  http://localhost:8000  (빌드된 프론트 서빙)
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.backend import serializers as ser
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
    return {
        "year": s.year, "day": season.day, "days_total": len(season.schedule),
        "user_tid": s.user_tid, "my_team": ser.team_summary(s.user_team),
        "my_rank": next(i for i, t in enumerate(season.standings(), 1)
                        if t.tid == s.user_tid),
        "next_games": upcoming, "news": s.news,
        "history": s.history, "postseason": s.postseason_summary,
        "has_offseason_report": bool(s.offseason_reports),
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
    out = sess().advance(req.unit)
    out["state"] = game_state()
    return out


@app.get("/api/standings")
def standings():
    return ser.standings_rows(sess().season.standings())


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
        for p in t.roster:
            if p.pid == pid:
                return ser.player_detail(p)
    raise HTTPException(404, f"선수 없음: {pid}")


@app.get("/api/results")
def results(day: int | None = None):
    s = sess()
    if not s.results_by_day:
        return {"day": 0, "games": []}
    idx = (len(s.results_by_day) - 1) if day is None else day - 1
    if not 0 <= idx < len(s.results_by_day):
        raise HTTPException(404, f"일자 범위 밖: {day}")
    return {"day": idx + 1, "last_day": len(s.results_by_day),
            "games": [ser.game_row(r) for r in s.results_by_day[idx]]}


@app.get("/api/results/{day}/{game_idx}")
def boxscore(day: int, game_idx: int):
    s = sess()
    try:
        return ser.boxscore(s.results_by_day[day - 1][game_idx])
    except IndexError:
        raise HTTPException(404, "경기 없음")


@app.get("/api/offseason/report")
def offseason_report():
    return sess().offseason_reports


# 빌드된 프론트 정적 서빙 (web/frontend/dist)
_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
