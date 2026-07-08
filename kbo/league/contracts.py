"""선수 가치 평가 — WAR × ($/WAR) (DESIGN_CONTRACTS.md §1).

이 단계의 심장. 능력치를 기대 WAR로 환산하고, 에이징 커브의 기대 궤적을
재사용해 잔여 전성기(미래가치)를 할인 합산한다 → 나이·potential이 자연 반영.
  war_now   : 올해 기대 WAR (단년 적정연봉의 근거)
  asset_war : 미래가치 할인 합산 (다년계약·트레이드·드래프트 자산가치)
선수·지명권을 같은 통화(WAR/억원)로 평가하는 value_of 디스패치 훅 포함.
시즌 간 로직 — 경기 엔진은 호출하지 않는다 (회귀 가드).
"""
from __future__ import annotations

from ..engine.probability import TUNE, clamp
from ..models.player import Player
from ..models.team import DraftPick, Team
from .aging import BAT_W, PIT_W, expected_delta, overall, _ratings


def _war_from_ovr(p: Player, ovr: float, role_pt: float) -> float:
    """OVR·역할·포지션 희소성 → 기대 WAR (대체선수 이하 = 0)."""
    c = TUNE["contract"]
    k = c["war_k_pit"] if p.is_pitcher else c["war_k_bat"]
    scar = c["scarcity"].get(p.pos, 1.0)
    return max(0.0, k * (ovr - c["ovr_repl"])) * role_pt * scar


def _future_ovr(p: Player, years: int) -> list[float]:
    """노이즈 제외 기대 궤적으로 age+1..age+years의 OVR 예측 (에이징 재사용)."""
    a = TUNE["aging"]
    weights = PIT_W if p.is_pitcher else BAT_W
    r = _ratings(p)
    vals = {n: getattr(r, n) for n in weights}
    out = []
    for t in range(1, years + 1):
        for n in vals:
            vals[n] = clamp(vals[n] + expected_delta(p, n, p.age + t),
                            a["rating_min"], a["rating_max"])
        out.append(sum(weights[n] * vals[n] for n in vals))
    return out


def war_now(p: Player, role_pt: float) -> float:
    return _war_from_ovr(p, overall(p), role_pt)


def asset_war(p: Player, role_pt: float, discount: float | None = None) -> float:
    """미래가치: 현재 + 향후 horizon년 기대 WAR을 할인 합산.

    discount 오버라이드 = 시간 선호 (트레이드 GM 관점: 윈나우는 미래를 강하게
    할인해 즉전을 선호, 리빌딩은 약하게 할인해 유망주를 선호 — DESIGN_TRADE.md §3).
    """
    c = TUNE["contract"]
    disc = c["discount"] if discount is None else discount
    total = _war_from_ovr(p, overall(p), role_pt)  # t=0 (현재)
    for t, ovr in enumerate(_future_ovr(p, c["horizon"]), start=1):
        total += _war_from_ovr(p, ovr, role_pt) / (1.0 + disc) ** t
    return total


def dollar_per_war(cap: float, year: int = 0) -> float:
    """$/WAR(억) = 리그캡 × 비율 × 감쇠. 캡 성장이 연봉에 전파되되, 리그 WAR
    총량이 대체로 일정하므로 연 damp만큼 완화해 실질 인플레를 캡에 정렬한다."""
    c = TUNE["contract"]
    return cap * c["cap_to_war_ratio"] * (1.0 - c["war_growth_damp"]) ** year


def fair_salary(p: Player, cap: float, role_pt: float, year: int = 0) -> float:
    """올해 적정 연봉(억) = max(최저연봉, war_now × $/WAR)."""
    c = TUNE["contract"]
    return max(c["min_salary"], war_now(p, role_pt) * dollar_per_war(cap, year))


def contract_value(p: Player, cap: float, role_pt: float, year: int = 0,
                   discount: float | None = None) -> float:
    """자산가치(억) = asset_war × $/WAR (다년계약·트레이드 비교 통화)."""
    return asset_war(p, role_pt, discount) * dollar_per_war(cap, year)


def team_roles(team: Team) -> dict:
    """로스터 OVR 순위로 출전 기대(역할) 배율 추정. {pid: role_pt}."""
    c = TUNE["contract"]
    roles: dict[str, float] = {}
    bats = sorted(team.batters, key=lambda x: x.bat_overall, reverse=True)
    for i, p in enumerate(bats):
        roles[p.pid] = (c["role_reg"] if i < 9 else
                        c["role_sub"] if i < 13 else c["role_bench"])
    for p in team.pitchers:
        roles[p.pid] = c["role_sp"] if p.pos == "SP" else c["role_rp"]
    return roles


def value_of(asset, cap: float, role_pt: float = 1.0, year: int = 0,
             discount: float | None = None, pick_mult: float = 1.0) -> float:
    """자산 통일 평가 디스패치 (DESIGN_CONTRACTS.md §6) — 선수·지명권 같은 통화(억원).

    선수 = §1 자산가치 (discount = 시간 선호 오버라이드). 지명권 = 라운드별
    기대 신인 WAR(시뮬 실측 역산, DESIGN_TRADE.md §4) × $/WAR × pick_mult
    (시간 선호: 미래 자산이라 윈나우 할인/리빌딩 프리미엄), 페널티 지명권 할인.
    """
    if isinstance(asset, Player):
        return contract_value(asset, cap, role_pt, year, discount)
    if isinstance(asset, DraftPick):
        tr = TUNE["trade"]
        war = tr["pick_war"].get(asset.round, 2.0)
        if asset.penalty:
            war *= tr["pick_penalty_mult"]
        return war * dollar_per_war(cap, year) * pick_mult
    raise TypeError(f"평가 불가 자산: {type(asset).__name__}")
