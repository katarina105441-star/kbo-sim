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
class DraftPick:
    """드래프트 지명권 자산 (DESIGN_CONTRACTS.md §6 훅).

    지금은 예약 필드만 — 평가/트레이드는 드래프트 단계. value_of() 디스패치가
    선수와 동일 통화(WAR/억원)로 지명권을 평가할 인터페이스를 위해 존재.
    """
    year: int
    round: int
    original_tid: str          # 원 소유 구단 (역순지명·트레이드 추적)
    penalty: bool = False      # 경쟁균형세 초과 페널티 지명권 여부


@dataclass
class Team:
    tid: str
    name: str
    city: str
    stadium: str
    park: ParkFactor
    budget: float
    # 재정 (DESIGN_CONTRACTS.md §4). market_size = 시장 크기 고정 오프셋
    # (1.0 = 리그 평균, 완만한 20~30% 격차). revenue = 전 시즌 수입(억).
    market_size: float = 1.0
    revenue: float = 0.0
    draft_picks: list = field(default_factory=list)   # DraftPick 자산 (§6 훅)
    roster: list[Player] = field(default_factory=list)
    # 라인업: 타순 9명. 각 항목 (선수, 수비 슬롯 or "DH")
    lineup: list[tuple[Player, str]] = field(default_factory=list)
    rotation: list[Player] = field(default_factory=list)   # 선발 5명 (순환)
    bullpen: list[Player] = field(default_factory=list)    # RP들
    closer: Optional[Player] = None
    setup: list[Player] = field(default_factory=list)      # 필승조 (불펜 부분집합)
    rot_idx: int = 0
    wins: int = 0
    losses: int = 0
    ties: int = 0
    user_managed: bool = False   # 유저 팀: 유저가 짠 타순/로테이션 유지 (UI 훅)

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

    def refresh_lineup(self) -> None:
        """경기 전 라인업 갱신. 유저 팀은 짜둔 타순 유지 — 부상자만 최고 백업 대체."""
        if not (self.user_managed and self.lineup):
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
            # 타순과 슬롯은 그대로 두고, 가능하면 같은 주포지션 백업을 우선한다.
            idx = next((i for i, sub in enumerate(subs) if sub.pos == slot), 0)
            refreshed.append((subs.pop(idx), slot))
        self.lineup = refreshed

    def build_default_pitching(self) -> None:
        healthy = [p for p in self.pitchers if p.inj_days == 0]
        sps = sorted([p for p in healthy if p.pos == "SP"],
                     key=lambda p: p.pit_overall, reverse=True)
        # 건강한 선발이 5명 미만이면 스태미나 높은 불펜을 스윙맨으로 추천한다.
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
        # 기본 추천은 기존 OVR 순서의 상위 2명이라 공유 모드의 투수 선택 결과를
        # 바꾸지 않는다. 유저가 편집한 경우에만 다른 필승조 힌트가 적용된다.
        self.setup = [p for p in self.bullpen if p.inj_days == 0][:2]

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
