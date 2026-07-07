"""동적 예산·경쟁균형세 — 시즌 간 재정 (DESIGN_CONTRACTS.md §3~5).

오프시즌 1회 offseason_finance_tick:
  연봉을 적정가(fair value)로 갱신 → 리그 캡 상향 → 구단 예산 동적 변동
  → 경쟁균형세(소프트캡) 제재 → 서비스타임 적립.
런어웨이 3중 차단: 캡/하한 하드 클램프 + EMA 완만 이동 + 변동폭 클램프.
시장차는 완만한 고정 오프셋일 뿐, 성적 기반 동적 변동이 지배적이어야 한다.
경기 엔진은 이 모듈을 호출하지 않는다 (단일 시즌 무영향, 회귀 가드).
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from ..engine.probability import TUNE, clamp
from ..models.team import Team
from .aging import ensure_talents, overall
from .contracts import fair_salary, team_roles

# 시장 크기 고정 오프셋 (완만한 20~30% 격차, 평균≈1.0). 수도권 큰손 vs 지방 짠물.
# 시장차는 출발점일 뿐 — 동적 예산이 지배적(짠물도 성공하면 큰손 수준 도달).
MARKET = {"LG": 1.15, "DSN": 1.15, "KWM": 1.15,   # 서울
          "SSG": 1.05, "KT": 1.05,                # 인천·수원
          "KIA": 0.90, "SAM": 0.90, "LTE": 0.90, "NC": 0.90, "HWE": 0.90}  # 지방


def init_market(teams: list[Team]) -> None:
    """teams.json 로드 후 1회 — 시장 오프셋·초기 예산 기준선 설정.

    teams.json의 budget은 척도가 달라, 캡 기준 중립 베이스라인(성적 0 가정,
    시장만 반영)으로 재설정해 시즌1이 캡 범위 안에서 출발하게 한다.
    """
    c = TUNE["contract"]
    cap = league_cap(0)
    for t in teams:
        t.market_size = MARKET.get(t.tid, 1.0)
        t.budget = round(clamp(cap * c["budget_base_share"] * t.market_size,
                               cap * c["floor_frac"], cap), 2)


def league_cap(year: int) -> float:
    """경쟁균형세 캡(억). 2025(year 0) 137억, 매년 +5%."""
    c = TUNE["contract"]
    return c["cap_year0"] * (1.0 + c["cap_growth"]) ** year


def team_payroll(team: Team) -> float:
    """상위 40명 AAV 총액(억). 로스터가 40명 미만이면 전원."""
    aavs = sorted((p.contract.aav for p in team.roster), reverse=True)[:40]
    return sum(aavs)


def _budget_target(team: Team, cap: float) -> float:
    """시장(완만) + 성적(지배적) 배분으로 목표 예산 산출 후 [하한,캡] 클램프."""
    c = TUNE["contract"]
    share = (c["budget_base_share"] * team.market_size
             + c["budget_win_share"] * (team.wins - 72) / 72.0)
    return clamp(cap * share, cap * c["floor_frac"], cap)


def update_budget(prev: float, target: float, cap: float) -> float:
    """EMA 완만 이동 + 시즌당 변동폭 클램프 + [하한,캡] 하드 클램프."""
    c = TUNE["contract"]
    moved = prev + c["ema_alpha"] * (target - prev)          # EMA
    swing = c["max_swing"] * prev
    moved = clamp(moved, prev - swing, prev + swing)         # 변동폭 클램프
    return clamp(moved, cap * c["floor_frac"], cap)          # 하드 클램프


def spending_ai(team: Team, rank: int, n_teams: int) -> tuple[float, list[str]]:
    """지출 성향 뼈대 (§5) — 적극성 스칼라 + 약점 포지션. 행동은 다음 단계.

    적극성 = 캡 여유 + 팀 단계(윈나우/리빌딩). 약점 = 해당 포지션 최고 OVR이
    로스터 포지션 중앙값 미달인 자리.
    """
    cap = league_cap(0)  # 상대 비교용 기준 캡
    cap_room = clamp((cap - team_payroll(team)) / cap, 0.0, 1.0)
    contend = 1.0 - (rank - 1) / max(1, n_teams - 1)   # 상위일수록 1에 근접(윈나우)
    core_age = sum(p.age for p in team.roster) / max(1, len(team.roster))
    win_now = contend * (1.0 if core_age >= 29 else 0.7)   # 노장 코어면 윈나우 가중
    aggressiveness = clamp(0.5 * cap_room + 0.5 * win_now, 0.0, 1.0)

    best_by_pos: dict[str, float] = {}
    for p in team.batters:
        best_by_pos[p.pos] = max(best_by_pos.get(p.pos, 0.0), p.bat_overall)
    if best_by_pos:
        med = sorted(best_by_pos.values())[len(best_by_pos) // 2]
        weak = [pos for pos, ov in best_by_pos.items() if ov < med]
    else:
        weak = []
    return aggressiveness, weak


@dataclass
class FinanceReport:
    cap: float = 0.0
    tax_payers: list = field(default_factory=list)   # [(tid, payroll, tax)]
    below_floor: list = field(default_factory=list)  # [tid]


def offseason_finance_tick(rng: random.Random, teams: list[Team],
                           year: int = 0) -> FinanceReport:
    """오프시즌 재정 처리 1회. 에이징 offseason_tick 이후 체인.

    현 단계 계약 모델: 연봉을 적정가로 갱신(중재/재계약 프록시). 다년 FA
    계약은 FA 단계 — 지금은 단년 갱신으로 리그 연봉 분포를 형성한다.
    """
    ensure_talents(rng, (p for t in teams for p in t.roster))
    cap = league_cap(year)
    c = TUNE["contract"]
    rep = FinanceReport(cap=cap)

    for t in teams:
        roles = team_roles(t)
        for p in t.roster:
            p.contract.salary = round(fair_salary(p, cap, roles[p.pid], year), 2)
            p.contract.years = max(1, p.contract.years)
            active = ((p.season_bat.pa > 0 or p.season_pit.outs > 0)
                      and p.missed <= c["fa_svc_max_missed"])
            p.service_years += 1.0 if active else 0.5

        target = _budget_target(t, cap)
        t.revenue = round(target, 2)
        t.budget = round(update_budget(t.budget, target, cap), 2)

        payroll = team_payroll(t)
        if payroll > cap:                      # 소프트캡 초과 → 제재금 + 지명권 페널티 훅
            tax = (payroll - cap) * c["luxury_rate"]
            t.revenue = round(t.revenue - tax, 2)
            for pk in t.draft_picks:           # §6 훅: 지명권 있으면 페널티 플래그
                pk.penalty = True
            rep.tax_payers.append((t.tid, round(payroll, 1), round(tax, 1)))
        if payroll < cap * c["floor_frac"]:    # 하한 미달
            rep.below_floor.append(t.tid)
    return rep
