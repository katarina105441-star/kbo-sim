"""에이징 커브 — 시즌 간(오프시즌) 능력치 변화 + 은퇴/스텁 신인 (DESIGN_AGING.md).

곡선: 능력치별 4구간 조각 선형 (성장 → 피크 0 → 완만 하락 → 급락).
개인차: 숨김 재능 g(성장 배율)·d(노쇠 내성, 하락에 (2−d) 배율) 1회 추첨
        + 연간 노이즈 N(0, σ) → 같은 나이라도 커리어가 갈린다.
시즌 중에는 아무 것도 하지 않는다 → 단일 시즌 캘리브레이션 무영향.
연간 변화가 소수 단위라 능력치는 오프시즌 이후 float로 누적된다.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from ..models.player import Player, Contract, BatterRatings, PitcherRatings
from ..models.team import Team
from ..engine.probability import TUNE, clamp, precompute_all

# OVR 가중치 (Player.bat_overall / pit_overall과 동일 — potential 궤적 계산용)
BAT_W = {"contact": 0.30, "power": 0.25, "eye": 0.20,
         "speed": 0.10, "fielding": 0.10, "arm": 0.05}
PIT_W = {"stuff": 0.30, "velocity": 0.25, "control": 0.25,
         "breaking": 0.10, "stamina": 0.10}
PROJECT_TO_AGE = 40  # potential 기대 궤적 투영 상한 (전 능력치 피크 종료 이후)


def overall(p: Player) -> float:
    return p.pit_overall if p.is_pitcher else p.bat_overall


def _curve_table(p: Player) -> dict:
    return TUNE["aging"]["pit_curve" if p.is_pitcher else "bat_curve"]


def _ratings(p: Player):
    return p.pit if p.is_pitcher else p.bat


def base_delta(curve: tuple, age: int, decline_shift: int = 0) -> float:
    """재능 미반영 연간 기본 변화량. decline_shift: 포수 등 하락 조기화(년)."""
    grow, peak_start, peak_end, mild, steep_from, steep = curve
    peak_end -= decline_shift
    steep_from -= decline_shift
    if age < peak_start:
        return grow
    if age <= peak_end:
        return 0.0
    if age < steep_from:
        return -mild
    return -steep


def expected_delta(p: Player, name: str, age: int) -> float:
    """재능(g/d) 반영, 노이즈 제외 연간 기대 변화량."""
    shift = TUNE["aging"]["catcher_shift"] if p.pos == "C" else 0
    d0 = base_delta(_curve_table(p)[name], age, shift)
    return d0 * p.tal_g if d0 > 0 else d0 * (2.0 - p.tal_d)


# ---------- 재능 추첨 ----------
def roll_talents(rng: random.Random, stub: bool = False,
                 elite: bool = False) -> tuple[float, float]:
    """(성장 g, 노쇠내성 d) 추첨. stub=고분산, elite=성장재능 상단 밴드."""
    a = TUNE["aging"]
    if elite:
        mu, sd, lo, hi = a["archetype"]["elite_g"]
    else:
        mu, sd, lo, hi = a["talent_g"]
        if stub:
            sd = a["stub_g_sd"]  # 스텁 신인: 스타 유망주와 bust 공존
    g = clamp(rng.gauss(mu, sd), lo, hi)
    mu, sd, lo, hi = a["talent_d"]
    d = clamp(rng.gauss(mu, sd), lo, hi)
    return g, d


def draw_talents(rng: random.Random, p: Player, stub: bool = False) -> None:
    p.tal_g, p.tal_d = roll_talents(rng, stub=stub)


def ensure_talents(rng: random.Random, players) -> None:
    """미추첨(tal_g==0) 선수에게 1회 추첨. 순회 순서 고정 → 시드 재현."""
    for p in players:
        if p.tal_g == 0.0:
            draw_talents(rng, p)


# ---------- Potential ----------
def potential(p: Player) -> float:
    """피크 예상 종합치 — 노이즈 제외 기대 궤적의 OVR 최댓값 (검증/표시용)."""
    a = TUNE["aging"]
    weights = PIT_W if p.is_pitcher else BAT_W
    r = _ratings(p)
    vals = {name: getattr(r, name) for name in weights}
    best = sum(weights[n] * v for n, v in vals.items())
    for age in range(p.age + 1, PROJECT_TO_AGE + 1):
        for name in vals:
            vals[name] = clamp(vals[name] + expected_delta(p, name, age),
                               a["rating_min"], a["rating_max"])
        best = max(best, sum(weights[n] * v for n, v in vals.items()))
    return best


# ---------- 연간 적용 ----------
def age_player(rng: random.Random, p: Player) -> None:
    """나이 +1 후 새 나이 기준으로 전 능력치에 곡선+노이즈 적용."""
    a = TUNE["aging"]
    p.age += 1
    r = _ratings(p)
    for name in (PIT_W if p.is_pitcher else BAT_W):
        delta = expected_delta(p, name, p.age) + rng.gauss(0.0, a["noise_sd"])
        delta = clamp(delta, -a["delta_clamp"], a["delta_clamp"])
        setattr(r, name, clamp(getattr(r, name) + delta,
                               a["rating_min"], a["rating_max"]))


# ---------- 은퇴 (3단 규칙) ----------
def should_retire(rng: random.Random, p: Player) -> bool:
    a = TUNE["aging"]
    if p.age >= a["retire_age_hard"]:
        return True
    if p.age >= a["retire_age_coin"] and rng.random() < 0.5:
        return True
    ovr = overall(p)
    soft_age, soft_ovr = a["retire_age_soft"]
    if p.age >= soft_age and ovr < soft_ovr:
        return True
    if ovr < a["replacement"]:  # 주 트리거: 대체선수 수준 미만
        if p.age < 30 and potential(p) >= a["retire_young_pot"]:
            return False  # 성장 여지 있는 유망주는 유예
        return True
    return False


# ---------- 신인 풀 생성 (정식 드래프트 재사용 프리미티브) ----------
def generate_prospect(rng: random.Random, is_pitcher: bool, pos: str = ""):
    """아키타입 3티어 신인 능력치 + 재능 + 티어 라벨 생성 (DESIGN_AGING.md §4).

    티어: 일반(대다수) / 특화형(시그니처만 극단, 원툴 → OVR 평균 → 드리프트 중립)
          / 특급(전반 상향 + 성장재능 상단). 반환 (ratings, tal_g, tal_d, tier).
    로스터/은퇴 플러밍과 무관 → 정식 드래프트가 신인 풀 생성에 그대로 재사용.
    pos: 향후 포지션별 아키타입(예: 포수 특화) 확장용 예약 인자.
    """
    a = TUNE["aging"]
    ar = a["archetype"]
    base = a["rookie_mean_pit"] if is_pitcher else a["rookie_mean_bat"]
    names = list(PIT_W if is_pitcher else BAT_W)

    def draw(mean: float, hi: float) -> float:
        return clamp(rng.gauss(mean, a["rookie_sd"]), a["rookie_lo"], hi)

    r = rng.random()
    if r < ar["elite_prob"]:                      # 특급 (극소수)
        tier = "elite"
        vals = {n: draw(base + ar["elite_off"], ar["elite_hi"]) for n in names}
        g, d = roll_talents(rng, elite=True)
    elif r < ar["elite_prob"] + ar["spec_prob"]:  # 특화형 (원툴)
        tier = "spec"
        sigs = rng.choice(ar["pit_sigs" if is_pitcher else "bat_sigs"])
        vals = {}
        for n in names:
            if n in sigs:
                vals[n] = clamp(rng.gauss(ar["sig_mean"], ar["sig_sd"]),
                                a["rookie_lo"], ar["sig_hi"])
            else:
                vals[n] = draw(base + ar["off_spec"], a["rookie_hi"])
        g, d = roll_talents(rng, stub=True)
    else:                                         # 일반 유망주
        tier = "common"
        vals = {n: draw(base, a["rookie_hi"]) for n in names}
        g, d = roll_talents(rng, stub=True)

    if is_pitcher:
        ratings = PitcherRatings(vals["velocity"], vals["control"], vals["stuff"],
                                 vals["stamina"], vals["breaking"])
    else:
        ratings = BatterRatings(vals["contact"], vals["power"], vals["eye"],
                                vals["speed"], vals["fielding"], vals["arm"])
    return ratings, g, d, tier


def make_rookie(rng: random.Random, tid: str, pos: str, seq: str) -> Player:
    """generate_prospect를 스텁 신인 Player로 포장 (1:1 은퇴 대체용)."""
    is_pit = pos in ("SP", "RP", "CL")
    ratings, g, d, _tier = generate_prospect(rng, is_pit, pos)
    bats = "S" if (r := rng.random()) < 0.05 else ("L" if r < 0.35 else "R")
    p = Player(
        pid=f"{tid}-{seq}", name=f"신인{seq}", team_id=tid, pos=pos,
        age=rng.randint(*TUNE["aging"]["rookie_age"]),
        bats=bats, throws="L" if rng.random() < 0.25 else "R",
        contract=Contract(0.3, 1), stub=True,
        pit=ratings if is_pit else None, bat=None if is_pit else ratings)
    p.tal_g, p.tal_d = g, d
    return p


# ---------- 오프시즌 틱 ----------
@dataclass
class OffseasonReport:
    retired: list = field(default_factory=list)   # [(Team, Player)]
    rookies: list = field(default_factory=list)   # [(Team, Player)]


def offseason_tick(rng: random.Random, teams: list[Team], year: int = 0) -> OffseasonReport:
    """시즌 종료 후 1회: 재능 추첨(최초) → 에이징 → 은퇴 → 1:1 스텁 신인.

    로스터 인원/포지션 구성이 보존된다. 라인업/로테이션은 다음 시즌
    시작(SeasonRunner.run)에서 재구성되므로 여기서 건드리지 않는다.
    """
    ensure_talents(rng, (p for t in teams for p in t.roster))
    rep = OffseasonReport()
    for t in teams:
        for p in t.roster:
            age_player(rng, p)
        keep, n_new = [], 0
        for p in t.roster:
            if should_retire(rng, p):
                rep.retired.append((t, p))
                rookie = make_rookie(rng, t.tid, p.pos, f"Y{year}N{n_new}")
                n_new += 1
                rep.rookies.append((t, rookie))
                keep.append(rookie)
            else:
                keep.append(p)
        t.roster = keep
    precompute_all(p for t in teams for p in t.roster)  # 능력치 변경 → 시프트 재계산
    return rep
