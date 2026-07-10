"""신인 드래프트 — 순수 역순(Z자) + Need 우선 지명 + 스카우팅 불확실성.

설계: DESIGN_DRAFT.md. 오프시즌 체인에서 에이징(은퇴, draft_mode=True) 뒤에
run_draft가 은퇴 구멍을 채운다: 투수 편중 풀을 generate_prospect로 생성 →
구단별 스카우팅 관측치 → Need·운영 성향 보정 지명 → 로스터 편입.
시즌 간 로직 — 경기 엔진은 호출하지 않는다 (회귀 가드).
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass

from ..engine.probability import TUNE, clamp, precompute_all
from ..models.player import Contract, Player
from ..models.team import Team
from .aging import generate_prospect, overall
from .contracts import asset_war
from .team_identity import (draft_fit_bonus, ensure_team_identities,
                            scouting_sigma)

FIELD_POS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
PIT_POS = ["SP", "RP", "CL"]
BAT_POS_W = {"C": 0.14, "SS": 0.14, "CF": 0.13, "2B": 0.12, "3B": 0.12,
             "RF": 0.12, "LF": 0.12, "1B": 0.11}
PIT_POS_W = {"SP": 0.62, "RP": 0.33, "CL": 0.05}


@dataclass
class DraftPickResult:
    year: int
    round: int
    tid: str
    player: Player
    scouted: float
    true_val: float
    need: float


def _pos_distribution(teams: list[Team]) -> dict:
    d = TUNE["draft"]
    base = {}
    for pos, w in PIT_POS_W.items():
        base[pos] = d["pitcher_frac"] * w
    for pos, w in BAT_POS_W.items():
        base[pos] = (1.0 - d["pitcher_frac"]) * w
    hole = {p: 0.0 for p in base}
    for team in teams:
        have = {}
        for player in team.roster:
            have[player.pos] = have.get(player.pos, 0) + 1
        for pos in base:
            target = 2 if pos == "SP" else 1
            if have.get(pos, 0) < target:
                hole[pos] += 1
    htot = sum(hole.values())
    if htot:
        blend = d["retire_blend"]
        for pos in base:
            base[pos] = (1 - blend) * base[pos] + blend * (hole[pos] / htot)
    total = sum(base.values())
    return {pos: weight / total for pos, weight in base.items()}


def build_pool(rng: random.Random, teams: list[Team], year: int) -> list[Player]:
    d = TUNE["draft"]
    holes = sum(max(0, 25 - len(team.roster)) for team in teams)
    size = int(clamp(holes * d["pool_factor"], d["pool_min"], d["pool_max"]))
    dist = _pos_distribution(teams)
    positions, weights = list(dist), list(dist.values())
    pool = []
    for i in range(size):
        pos = rng.choices(positions, weights)[0]
        is_pitcher = pos in PIT_POS
        ratings, growth, decline, _tier = generate_prospect(rng, is_pitcher, pos)
        draw = rng.random()
        bats = "S" if draw < 0.05 else ("L" if draw < 0.35 else "R")
        player = Player(
            pid=f"D{year}-{i}", name=f"신인{year}-{i}", team_id="", pos=pos,
            age=rng.randint(*TUNE["aging"]["rookie_age"]), bats=bats,
            throws="L" if rng.random() < 0.25 else "R",
            contract=Contract(TUNE["contract"]["min_salary"], 1), stub=True,
            pit=ratings if is_pitcher else None,
            bat=None if is_pitcher else ratings,
        )
        player.tal_g, player.tal_d = growth, decline
        pool.append(player)
    return pool


def _scout_with_sigma(rng: random.Random, pool: list[Player], sigma: float) -> dict:
    board = {}
    for player in pool:
        true_value = asset_war(player, 1.0)
        board[player.pid] = (
            true_value * math.exp(rng.gauss(0.0, sigma)), true_value)
    return board


def scout(rng: random.Random, pool: list[Player]) -> dict:
    """기존 컨센서스 보드. RNG 호환과 외부 검증용으로 유지한다."""
    return _scout_with_sigma(rng, pool, TUNE["draft"]["scout_noise"])


def scout_for_team(rng: random.Random, pool: list[Player], team: Team) -> dict:
    """구단 스카우팅 역량이 반영된 독립 관측 보드."""
    sigma = scouting_sigma(team, TUNE["draft"]["scout_noise"])
    return _scout_with_sigma(rng, pool, sigma)


def _depth(team: Team, pos: str) -> float:
    if pos in PIT_POS:
        group = ("SP",) if pos == "SP" else ("RP", "CL")
        candidates = [overall(player) for player in team.roster
                      if player.pos in group]
    else:
        candidates = [overall(player) for player in team.roster
                      if player.pos == pos]
    return max(candidates) if candidates else 0.0


def need_bonus(team: Team, pos: str) -> float:
    d = TUNE["draft"]
    need = clamp((d["need_ref"] - _depth(team, pos)) / d["need_span"], 0.0, 1.0)
    return need * d["need_max_bonus"]


def round_need_mult(rnd: int) -> float:
    d = TUNE["draft"]
    if rnd < d["round_mid_start"]:
        return d["need_mult_early"]
    if rnd < d["round_late_start"]:
        return d["need_mult_mid"]
    return d["need_mult_late"]


def ceiling_bonus(player: Player, rnd: int) -> float:
    d = TUNE["draft"]
    if rnd < d["round_late_start"]:
        return 0.0
    low, high = TUNE["aging"]["rookie_age"]
    youth = clamp((high - player.age) / (high - low), 0.0, 1.0) if high > low else 0.0
    return d["ceiling_bonus"] * youth


def _sign(player: Player, team: Team) -> None:
    player.team_id = team.tid
    team.roster.append(player)


def run_draft(rng: random.Random, teams: list[Team], standings: list[Team],
              year: int) -> list[DraftPickResult]:
    """역순 드래프트. 콘솔·웹 자동 경로 모두 같은 구단별 성향을 사용한다."""
    ensure_team_identities(teams)
    d = TUNE["draft"]
    pool = build_pool(rng, teams, year)
    scout(rng, pool)  # 기존 RNG 소비 순서를 보존하는 컨센서스 보드
    boards = {team.tid: scout_for_team(rng, pool, team) for team in teams}
    order = list(reversed(standings))
    target = {team.tid: 25 for team in teams}
    by_tid = {team.tid: team for team in teams}
    owner = {(pick.round, pick.original_tid): team.tid
             for team in teams for pick in team.draft_picks if pick.year == year}
    results: list[DraftPickResult] = []

    for rnd in range(1, d["rounds"] + 1):
        for slot in order:
            team = by_tid[owner.get((rnd, slot.tid), slot.tid)]
            if len(team.roster) >= target[team.tid] or not pool:
                continue
            n_batters = sum(1 for player in team.roster if not player.is_pitcher)
            n_pitchers = len(team.roster) - n_batters
            need_batter = n_batters < d["roster_bat"]
            need_pitcher = n_pitchers < d["roster_pit"]
            candidates = [
                player for player in pool
                if (need_batter and not player.is_pitcher)
                or (need_pitcher and player.is_pitcher)
            ] or pool
            multiplier = round_need_mult(rnd)
            board = boards[team.tid]
            best = None
            best_score = -1e9
            best_need = 0.0
            for player in candidates:
                raw_need = need_bonus(team, player.pos)
                score = (board[player.pid][0]
                         + raw_need * multiplier
                         + ceiling_bonus(player, rnd)
                         + draft_fit_bonus(team, player, rnd))
                if score > best_score:
                    best, best_score, best_need = player, score, raw_need
            pool.remove(best)
            scouted, true_value = board[best.pid]
            _sign(best, team)
            results.append(DraftPickResult(
                year, rnd, team.tid, best, scouted, true_value, best_need))
    precompute_all(player for team in teams for player in team.roster)
    return results
