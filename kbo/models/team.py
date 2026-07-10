"""팀 모델 — 1군·2군 로스터, 라인업, 로테이션, 불펜 역할."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .player import Player

FIELD_SLOTS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]  # DH 제외 수비 8자리


@dataclass
class ParkFactor:
    hr: float = 1.0
    xbh: float = 1.0


@dataclass
class DraftPick:
    """드래프트 지명권 자산."""
    year: int
    round: int
    original_tid: str
    penalty: bool = False


@dataclass
class Team:
    tid: str
    name: str
    city: str
    stadium: str
    park: ParkFactor
    budget: float
    market_size: float = 1.0
    revenue: float = 0.0
    draft_picks: list = field(default_factory=list)
    roster: list[Player] = field(default_factory=list)       # 1군
    minors: list[Player] = field(default_factory=list)       # 2군·육성
    lineup: list[tuple[Player, str]] = field(default_factory=list)
    rotation: list[Player] = field(default_factory=list)
    bullpen: list[Player] = field(default_factory=list)
    closer: Optional[Player] = None
    setup: list[Player] = field(default_factory=list)
    rot_idx: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    user_managed: bool = False
    identity: object | None = None

    @property
    def batters(self) -> list[Player]:
        return [p for p in self.roster if not p.is_pitcher]

    @property
    def pitchers(self) -> list[Player]:
        return [p for p in self.roster if p.is_pitcher]

    @property
    def all_players(self) -> list[Player]:
        return list(self.roster) + list(self.minors)

    def build_default_lineup(self) -> None:
        pool = sorted([p for p in self.batters if p.inj_days == 0],
                      key=lambda p: p.bat_overall, reverse=True)
        if len(pool) < 9:
            hurt = sorted([p for p in self.batters if p.inj_days > 0],
                          key=lambda p: p.inj_days)
            pool += hurt[:9 - len(pool)]
        used: set[str] = set()
        assign: dict[str, Player] = {}
        for slot in FIELD_SLOTS:
            cand = next((p for p in pool if p.pid not in used and p.pos == slot), None)
            if cand is None:
                cand = next((p for p in pool if p.pid not in used), None)
            if cand:
                assign[slot] = cand
                used.add(cand.pid)
        dh = next((p for p in pool if p.pid not in used), None)
        nine: list[tuple[Player, str]] = [(p, s) for s, p in assign.items()]
        if dh:
            nine.append((dh, "DH"))
        if not nine:
            self.lineup = []
            return

        def pick(key):
            best = max(nine, key=key)
            nine.remove(best)
            return best

        order = []
        b = lambda t: t[0].bat
        order.append(pick(lambda t: b(t).eye * 0.5 + b(t).speed * 0.5))
        if nine:
            order.append(pick(lambda t: b(t).contact))
        if nine:
            order.append(pick(lambda t: t[0].bat_overall))
        if nine:
            order.append(pick(lambda t: b(t).power))
        order.extend(sorted(nine, key=lambda t: t[0].bat_overall, reverse=True))
        self.lineup = order

    def refresh_lineup(self) -> None:
        if not (self.user_managed and self.lineup):
            self.build_default_lineup()
            return
        active = {p.pid for p in self.roster}
        self.lineup = [(p, slot) for p, slot in self.lineup if p.pid in active]
        if len(self.lineup) < 9:
            self.build_default_lineup()
            return
        used = {p.pid for p, _ in self.lineup}
        subs = sorted([p for p in self.batters
                       if p.inj_days == 0 and p.pid not in used],
                      key=lambda p: p.bat_overall, reverse=True)
        refreshed = []
        for p, slot in self.lineup:
            if p.inj_days == 0 or not subs:
                refreshed.append((p, slot))
                continue
            idx = next((i for i, sub in enumerate(subs) if sub.pos == slot), 0)
            refreshed.append((subs.pop(idx), slot))
        self.lineup = refreshed

    def build_default_pitching(self) -> None:
        healthy = [p for p in self.pitchers if p.inj_days == 0]
        sps = sorted([p for p in healthy if p.pos == "SP"],
                     key=lambda p: p.pit_overall, reverse=True)
        swing = sorted([p for p in healthy if p not in sps],
                       key=lambda p: (p.pit.stamina, p.pit_overall), reverse=True)
        self.rotation = (sps + swing)[:5]
        self.closer = next((p for p in healthy
                            if p.pos == "CL" and p not in self.rotation), None)
        if self.closer is None:
            self.closer = next((p for p in sorted(healthy,
                                                  key=lambda x: x.pit_overall,
                                                  reverse=True)
                                if p not in self.rotation), None)
        self.bullpen = sorted(
            [p for p in self.pitchers if p is not self.closer and p not in self.rotation],
            key=lambda p: p.pit_overall, reverse=True)
        self.setup = [p for p in self.bullpen if p.inj_days == 0][:2]

    def next_starter(self, advance: bool = True) -> Player:
        if not self.rotation:
            self.build_default_pitching()
        if not self.rotation:
            raise RuntimeError(f"{self.tid}에 등판 가능한 투수가 없습니다.")
        n = len(self.rotation)
        sp = self.rotation[self.rot_idx % n]
        if advance:
            self.rot_idx = (self.rot_idx + 1) % n
        if sp.inj_days == 0:
            return sp
        subs = [p for p in self.pitchers if p.inj_days == 0 and p not in self.rotation]
        if subs:
            return max(subs, key=lambda p: (p.pit.stamina, p.pit_overall))
        healthy_rot = [p for p in self.rotation if p.inj_days == 0]
        if healthy_rot:
            return healthy_rot[0]
        return sp

    @property
    def pct(self) -> float:
        d = self.wins + self.losses
        return self.wins / d if d else 0.0

    def reset_season(self) -> None:
        self.wins = self.losses = self.ties = 0
        self.rot_idx = 0
        for p in self.all_players:
            p.reset_season()
