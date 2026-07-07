"""신인 드래프트 — 순수 역순(Z자) + Need 우선 지명 + 스카우팅 불확실성.

설계: DESIGN_DRAFT.md. 오프시즌 체인에서 에이징(은퇴, draft_mode=True) 뒤에
run_draft가 은퇴 구멍을 채운다: 투수 편중 풀을 generate_prospect로 생성 →
컨센서스 스카우팅 관측치(로그정규 노이즈) → 팀별 Need 보정 지명 → 로스터 편입.
시즌 간 로직 — 경기 엔진은 호출하지 않는다 (회귀 가드).
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from ..engine.probability import TUNE, clamp, precompute_all
from ..models.player import BATTER_POS, Contract, Player
from ..models.team import Team
from .aging import generate_prospect, overall
from .contracts import asset_war

FIELD_POS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]   # DH는 신인 풀 제외
PIT_POS = ["SP", "RP", "CL"]
# 야수 풀 내 포지션 배분 (C·SS 등 키포지션 희소하게, 실제 아마 분포 근사)
BAT_POS_W = {"C": 0.14, "SS": 0.14, "CF": 0.13, "2B": 0.12, "3B": 0.12,
             "RF": 0.12, "LF": 0.12, "1B": 0.11}
PIT_POS_W = {"SP": 0.62, "RP": 0.33, "CL": 0.05}


@dataclass
class DraftPickResult:
    year: int
    round: int
    tid: str
    player: Player
    scouted: float     # 스카우팅 관측 가치 (지명 근거)
    true_val: float    # 실제 asset_war (사후 bust/대박 판정용)
    need: float        # 지명 시 Need 보너스


def _pos_distribution(teams: list[Team]) -> dict:
    """모집단 투수편중(기본) + 은퇴 구멍 분포 블렌드 → 포지션별 생성 확률."""
    d = TUNE["draft"]
    base = {}
    for pos, w in PIT_POS_W.items():
        base[pos] = d["pitcher_frac"] * w
    for pos, w in BAT_POS_W.items():
        base[pos] = (1.0 - d["pitcher_frac"]) * w
    # 은퇴 구멍(현재 로스터에서 부족한 포지션) 분포
    hole = {p: 0.0 for p in base}
    for t in teams:
        have = {}
        for p in t.roster:
            have[p.pos] = have.get(p.pos, 0) + 1
        for pos in base:
            target = 2 if pos in ("SP",) else 1
            if have.get(pos, 0) < target:
                hole[pos] += 1
    htot = sum(hole.values())
    if htot:
        blend = d["retire_blend"]
        for pos in base:
            base[pos] = (1 - blend) * base[pos] + blend * (hole[pos] / htot)
    tot = sum(base.values())
    return {pos: w / tot for pos, w in base.items()}


def build_pool(rng: random.Random, teams: list[Team], year: int) -> list[Player]:
    """지명 가치 있는 상위 풀만 생성 (150~200명, 투수편중+은퇴보정)."""
    d = TUNE["draft"]
    holes = sum(max(0, 25 - len(t.roster)) for t in teams)
    size = int(clamp(holes * d["pool_factor"], d["pool_min"], d["pool_max"]))
    dist = _pos_distribution(teams)
    positions, weights = list(dist), list(dist.values())
    pool = []
    for i in range(size):
        pos = rng.choices(positions, weights)[0]
        is_pit = pos in PIT_POS
        ratings, g, dd, _tier = generate_prospect(rng, is_pit, pos)
        bats = "S" if (r := rng.random()) < 0.05 else ("L" if r < 0.35 else "R")
        p = Player(pid=f"D{year}-{i}", name=f"신인{year}-{i}", team_id="", pos=pos,
                   age=rng.randint(*TUNE["aging"]["rookie_age"]),
                   bats=bats, throws="L" if rng.random() < 0.25 else "R",
                   contract=Contract(TUNE["contract"]["min_salary"], 1), stub=True,
                   pit=ratings if is_pit else None,
                   bat=None if is_pit else ratings)
        p.tal_g, p.tal_d = g, dd
        pool.append(p)
    return pool


def scout(rng: random.Random, pool: list[Player]) -> dict:
    """컨센서스 드래프트 보드 — 유망주별 스카우팅 관측치 1회 추첨.

    scouted = true_asset_war × exp(N(0, σ)). 진짜 재능(g/d) 불확실성 대리.
    """
    sigma = TUNE["draft"]["scout_noise"]
    board = {}
    for p in pool:
        true_v = asset_war(p, 1.0)             # 주전 가정 role=1.0
        board[p.pid] = (true_v * math.exp(rng.gauss(0.0, sigma)), true_v)
    return board


def _depth(team: Team, pos: str) -> float:
    """팀의 해당 포지션 최고 OVR (구멍이면 0). 투수는 SP/RP 그룹."""
    if pos in PIT_POS:
        grp = ("SP",) if pos == "SP" else ("RP", "CL")
        cands = [overall(p) for p in team.roster if p.pos in grp]
    else:
        cands = [overall(p) for p in team.roster if p.pos == pos]
    return max(cands) if cands else 0.0


def need_bonus(team: Team, pos: str) -> float:
    """Need = clamp((ref − depth)/span, 0, 1) × max_bonus (WAR 환산)."""
    d = TUNE["draft"]
    n = clamp((d["need_ref"] - _depth(team, pos)) / d["need_span"], 0.0, 1.0)
    return n * d["need_max_bonus"]


def _sign(p: Player, team: Team) -> None:
    p.team_id = team.tid
    team.roster.append(p)


def run_draft(rng: random.Random, teams: list[Team], standings: list[Team],
              year: int) -> list[DraftPickResult]:
    """역순(Z자) 11라운드 지명. standings: 전 시즌 순위(우승→꼴찌)."""
    d = TUNE["draft"]
    pool = build_pool(rng, teams, year)
    board = scout(rng, pool)
    order = list(reversed(standings))          # 꼴찌 먼저
    target = {t.tid: 25 for t in teams}
    results: list[DraftPickResult] = []

    for rnd in range(1, d["rounds"] + 1):
        for t in order:
            if len(t.roster) >= target[t.tid] or not pool:
                continue
            # 로스터 구성 보장: 부족한 타입만 후보로 (14야수/11투수 유지)
            n_bat = sum(1 for p in t.roster if not p.is_pitcher)
            n_pit = len(t.roster) - n_bat
            need_bat = n_bat < d["roster_bat"]
            need_pit = n_pit < d["roster_pit"]
            cands = [p for p in pool
                     if (need_bat and not p.is_pitcher) or (need_pit and p.is_pitcher)]
            if not cands:                     # 한 타입이 풀에서 소진된 극단 상황
                cands = pool
            best, best_score, best_need = None, -1e9, 0.0
            for p in cands:
                nb = need_bonus(t, p.pos)
                score = board[p.pid][0] + nb
                if score > best_score:
                    best, best_score, best_need = p, score, nb
            pool.remove(best)
            sc, tv = board[best.pid]
            _sign(best, t)
            results.append(DraftPickResult(year, rnd, t.tid, best, sc, tv, best_need))
    precompute_all(p for t in teams for p in t.roster)   # 신규 편입 시프트 계산
    return results
