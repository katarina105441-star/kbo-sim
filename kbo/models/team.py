"""팀 모델 — 로스터, 라인업(타순+수비 위치), 로테이션, 불펜 역할."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .player import Player

FIELD_SLOTS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]  # DH 제외 수비 8자리


@dataclass
class ParkFactor:
    hr: float = 1.0    # 홈런 배율 (1단계: 전 구장 중립 1.0, 뼈대만)
    xbh: float = 1.0   # 장타(2·3루타) 배율


@dataclass
class Team:
    tid: str
    name: str
    city: str
    stadium: str
    park: ParkFactor
    budget: float
    roster: list[Player] = field(default_factory=list)
    # 라인업: 타순 9명. 각 항목 (선수, 수비 슬롯 or "DH")
    lineup: list[tuple[Player, str]] = field(default_factory=list)
    rotation: list[Player] = field(default_factory=list)   # 선발 5명 (순환)
    bullpen: list[Player] = field(default_factory=list)    # RP들
    closer: Optional[Player] = None
    rot_idx: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0

    @property
    def batters(self) -> list[Player]:
        return [p for p in self.roster if not p.is_pitcher]

    @property
    def pitchers(self) -> list[Player]:
        return [p for p in self.roster if p.is_pitcher]

    def build_default_lineup(self) -> None:
        """수비 8슬롯에 주포지션 최적자 배치 + 최고 남은 타자 DH.

        부상자는 제외하고 건강한 백업이 자동 대체 (뎁스 활용).
        타순 휴리스틱: 1번 출루+주루, 2번 컨택, 3번 종합 최강, 4번 파워, 이후 종합순.
        """
        pool = sorted([p for p in self.batters if p.inj_days == 0],
                      key=lambda p: p.bat_overall, reverse=True)
        if len(pool) < 9:  # 극단적 연쇄 부상: 복귀 임박자부터 출전 강행
            hurt = sorted([p for p in self.batters if p.inj_days > 0],
                          key=lambda p: p.inj_days)
            pool += hurt[:9 - len(pool)]
        used: set[str] = set()
        assign: dict[str, Player] = {}
        for slot in FIELD_SLOTS:
            cand = next((p for p in pool if p.pid not in used and p.pos == slot), None)
            if cand is None:  # 주포지션 적임자 없으면 남은 최고 타자
                cand = next((p for p in pool if p.pid not in used), None)
            if cand:
                assign[slot] = cand
                used.add(cand.pid)
        dh = next((p for p in pool if p.pid not in used), None)
        nine: list[tuple[Player, str]] = [(p, s) for s, p in assign.items()]
        if dh:
            nine.append((dh, "DH"))

        def pick(key):
            best = max(nine, key=key)
            nine.remove(best)
            return best

        order = []
        b = lambda t: t[0].bat
        order.append(pick(lambda t: b(t).eye * 0.5 + b(t).speed * 0.5))       # 1번
        order.append(pick(lambda t: b(t).contact))                            # 2번
        order.append(pick(lambda t: t[0].bat_overall))                        # 3번
        order.append(pick(lambda t: b(t).power))                              # 4번
        order.extend(sorted(nine, key=lambda t: t[0].bat_overall, reverse=True))
        self.lineup = order

    def build_default_pitching(self) -> None:
        sps = sorted([p for p in self.pitchers if p.pos == "SP"],
                     key=lambda p: p.pit_overall, reverse=True)
        self.rotation = sps[:5]
        self.closer = next((p for p in self.pitchers if p.pos == "CL"), None)
        self.bullpen = sorted(
            [p for p in self.pitchers if p is not self.closer and p not in self.rotation],
            key=lambda p: p.pit_overall, reverse=True)

    def next_starter(self, advance: bool = True) -> Player:
        """로테이션 순서 고정. 예정 선발이 부상이면 불펜 스윙맨이 땜빵 선발.

        (건강한 에이스가 부상자 등판을 흡수해 등판 수가 부풀지 않도록 —
        실제 구단처럼 6선발/스윙맨을 올린다.)
        """
        n = len(self.rotation)
        sp = self.rotation[self.rot_idx % n]
        if advance:
            self.rot_idx = (self.rot_idx + 1) % n
        if sp.inj_days == 0:
            return sp
        subs = [p for p in self.pitchers if p.inj_days == 0 and p not in self.rotation]
        if subs:  # 스태미나 높은 스윙맨 우선
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
        for p in self.roster:
            p.reset_season()
