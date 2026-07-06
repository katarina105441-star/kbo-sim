"""투수 등판부하 추적기 — 정규시즌/포스트시즌 공용.

선발 등판일(등판간격)과 불펜 사용 이력(연투)을 추적해
경기 엔진에 넘길 가용/피로 컨텍스트를 만든다.
"""
from __future__ import annotations
from typing import Optional

from ..engine.probability import TUNE
from ..models.team import Team


class PitcherUsageTracker:
    def __init__(self):
        self.usage: dict[str, tuple[int, int, int]] = {}   # pid -> (마지막 등판일, 투구수, 연투수)
        self.last_start: dict[str, int] = {}               # pid -> 마지막 선발 등판일

    def track(self, res, day: int) -> None:
        for side in ("home", "away"):
            for i, st in enumerate(res.stints[side]):
                p = st.player
                if i == 0:
                    self.last_start[p.pid] = day
                    continue
                rec = self.usage.get(p.pid)
                streak = rec[2] + 1 if rec and rec[0] == day - 1 else 1
                self.usage[p.pid] = (day, st.line.pitches, streak)

    def rest_of(self, p, day: int) -> Optional[int]:
        """마지막 선발 등판 이후 휴식일. 선발 이력 없으면 None(충분한 휴식)."""
        ls = self.last_start.get(p.pid)
        return None if ls is None else day - ls - 1

    def unavailable(self, team: Team, day: int) -> set:
        """당일 등판 불가 투수 (부상 + 불펜 강행 한계 초과)."""
        out = set()
        hard = TUNE["fatigue"]["relief"]["hard_pitch"]
        for p in team.pitchers:
            if p.inj_days > 0:
                out.add(p.pid)
                continue
            if p.pos == "SP":
                continue
            rec = self.usage.get(p.pid)
            if rec and rec[0] == day - 1 and (rec[1] >= hard or rec[2] >= 2):
                out.add(p.pid)
        return out

    def ctx(self, team: Team, day: int) -> dict:
        """등판간격 컨텍스트: 선발 휴식일 → 한계 배율, 불펜 연투 → 입장 피로."""
        rest_tbl = TUNE["fatigue"]["rest"]
        rel = TUNE["fatigue"]["relief"]
        ctx: dict = {}
        for p in team.pitchers:
            ent: dict = {}
            r = self.rest_of(p, day)
            if r is not None:
                tbl = rest_tbl[min(6, max(3, r))]
                if tbl["mult"] != 1.0 or tbl["pen"] != 0.0:
                    ent = {"mult": tbl["mult"], "pen": tbl["pen"]}
            rec = self.usage.get(p.pid)
            if rec and rec[0] == day - 1:  # 어제 불펜 등판 → 오늘 저하 상태로 시작
                pen = rel["day1_base"] + rec[1] * rel["day1_per_pitch"]
                if rec[2] >= 2:
                    pen += rel["streak2"]
                ent["pen"] = ent.get("pen", 0.0) + pen
            if ent:
                ctx[p.pid] = ent
        return ctx
