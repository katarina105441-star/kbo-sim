"""선수 모델. 능력치는 0~100, 리그 평균 = 50 (엔진의 log5 수식 기준점).

능력치 산정 근거는 data/RATINGS_METHOD.md 참고.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .stats import BattingLine, PitchingLine

BATTER_POS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
PITCHER_POS = {"SP", "RP", "CL"}
HANDS = {"L", "R", "S"}


@dataclass
class Contract:
    salary: float             # 연봉 (억원)
    years: int                # 잔여 계약기간
    signing_bonus: float = 0.0  # 계약금 (억원, 다년계약 AAV 산정용)

    @property
    def aav(self) -> float:
        """캡 산정용 연평균가치 = (연봉×연수 + 계약금) / 연수. 단년이면 연봉."""
        n = max(1, self.years)
        return (self.salary * n + self.signing_bonus) / n


@dataclass
class BatterRatings:
    contact: int   # 컨택
    power: int     # 파워
    eye: int       # 선구안
    speed: int     # 주루
    fielding: int  # 수비
    arm: int       # 송구


@dataclass
class PitcherRatings:
    velocity: int  # 구속
    control: int   # 제구
    stuff: int     # 구위
    stamina: int   # 스태미나
    breaking: int  # 변화구


@dataclass
class Player:
    pid: str
    name: str
    team_id: str
    pos: str                 # 주 포지션 (BATTER_POS | PITCHER_POS)
    age: int
    bats: str                # L/R/S
    throws: str              # L/R
    contract: Contract
    bat: Optional[BatterRatings] = None
    pit: Optional[PitcherRatings] = None
    est: bool = False        # 능력치가 추정치인지
    basis: str = ""          # 능력치 산정 근거 (실제 성적)
    stub: bool = False       # 스텁 신인 (정식 드래프트 도입 시 교체 대상)
    # 숨김 재능 (에이징 커브 개인차, DESIGN_AGING.md §2). 0.0 = 미추첨.
    # UI/리포트 비노출 — 이후 스카우팅 불확실성의 기초.
    tal_g: float = 0.0       # 성장 재능 [0.3~1.7]
    tal_d: float = 0.0       # 노쇠 내성 [0.5~1.6]
    # FA 서비스타임 (DESIGN_CONTRACTS.md §8 / DESIGN_FA.md). 오프시즌에 활성시즌
    # (1군 등록 ≥145일 상당) 1시즌당 +1 적립.
    service_years: float = 0.0
    fa_eligible_at: float = 0.0   # 재자격 서비스 임계 (FA 계약 시 +reelig로 미룸)
    fa_grade: str = ""            # 직전 FA 시장 등급 A/B/C (검증·표시용)
    form_season: float = 0.0  # 시즌 폼 편차 (시즌 시작 시 추첨, gauss(0,1) 클램프)
    form_day: float = 0.0     # 일일 핫/콜드 (OU 프로세스, 정상상태 sd≈1)
    inj_days: int = 0        # 잔여 결장일 (0 = 건강)
    missed: int = 0          # 이번 시즌 결장 경기 수 (검증용)
    season_bat: BattingLine = field(default_factory=BattingLine)
    season_pit: PitchingLine = field(default_factory=PitchingLine)
    ps_bat: BattingLine = field(default_factory=BattingLine)    # 포스트시즌 기록 (분리 집계)
    ps_pit: PitchingLine = field(default_factory=PitchingLine)
    # 엔진이 캐싱하는 로그오즈 시프트 (probability.precompute_*가 채움)
    shifts: dict = field(default_factory=dict)

    def __post_init__(self):
        assert self.pos in BATTER_POS | PITCHER_POS, f"잘못된 포지션: {self.pos}"
        assert self.bats in HANDS and self.throws in {"L", "R"}

    @property
    def is_pitcher(self) -> bool:
        return self.pos in PITCHER_POS

    @property
    def bat_overall(self) -> float:
        b = self.bat
        if not b:
            return 0.0
        return (0.30 * b.contact + 0.25 * b.power + 0.20 * b.eye
                + 0.10 * b.speed + 0.10 * b.fielding + 0.05 * b.arm)

    @property
    def pit_overall(self) -> float:
        p = self.pit
        if not p:
            return 0.0
        return (0.30 * p.stuff + 0.25 * p.velocity + 0.25 * p.control
                + 0.10 * p.breaking + 0.10 * p.stamina)

    def reset_season(self) -> None:
        self.season_bat = BattingLine()
        self.season_pit = PitchingLine()
        self.ps_bat = BattingLine()
        self.ps_pit = PitchingLine()
        self.inj_days = 0
        self.missed = 0
        self.form_season = 0.0
        self.form_day = 0.0
