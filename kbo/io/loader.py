"""JSON 데이터 → 모델 객체 로딩 + 엔진 캐시(로짓 시프트) 준비."""
from __future__ import annotations
import json
import os

from ..models.player import Player, Contract, BatterRatings, PitcherRatings
from ..models.team import Team, ParkFactor
from ..engine.probability import precompute_all

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def load_league(data_dir: str = DATA_DIR) -> list[Team]:
    with open(os.path.join(data_dir, "teams.json"), encoding="utf-8") as f:
        tmeta = json.load(f)
    with open(os.path.join(data_dir, "players.json"), encoding="utf-8") as f:
        pdata = json.load(f)

    teams: list[Team] = []
    for tid, meta in tmeta.items():
        team = Team(
            tid=tid, name=meta["name"], city=meta["city"], stadium=meta["stadium"],
            park=ParkFactor(hr=meta["park"]["hr"], xbh=meta["park"]["xbh"]),
            budget=meta["budget"])
        rows = pdata[tid]
        for i, row in enumerate(rows["batters"]):
            b = row["bat"]
            team.roster.append(Player(
                pid=f"{tid}-B{i}", name=row["name"], team_id=tid, pos=row["pos"],
                age=row["age"], bats=row["bats"], throws=row["throws"],
                contract=Contract(row["sal"], row["yrs"]),
                bat=BatterRatings(b["con"], b["pow"], b["eye"], b["spd"], b["fld"], b["arm"]),
                est=row.get("est", False), basis=row.get("basis", "")))
        for i, row in enumerate(rows["pitchers"]):
            t = row["pit"]
            team.roster.append(Player(
                pid=f"{tid}-P{i}", name=row["name"], team_id=tid, pos=row["pos"],
                age=row["age"], bats=row["bats"], throws=row["throws"],
                contract=Contract(row["sal"], row["yrs"]),
                pit=PitcherRatings(t["vel"], t["ctl"], t["stf"], t["sta"], t["brk"]),
                est=row.get("est", False), basis=row.get("basis", "")))
        team.build_default_lineup()
        team.build_default_pitching()
        teams.append(team)

    precompute_all(p for t in teams for p in t.roster)
    return teams


def team_by_id(teams: list[Team], tid: str) -> Team:
    for t in teams:
        if t.tid.upper() == tid.upper():
            return t
    raise KeyError(f"팀 ID 없음: {tid} (사용 가능: {', '.join(t.tid for t in teams)})")
