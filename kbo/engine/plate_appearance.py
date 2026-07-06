"""타석 해결 트리 — 한 타석을 단계적으로 해결해 PAResult를 반환.

순서: ①사구 ②삼진/볼넷 ③홈런 ④타구유형 ⑤BABIP(수비 개입)
      ⑥안타 종류 ⑦병살/희생플라이/진루타 ⑧주자 처리
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..models.player import Player
from . import probability as prob
from .baserunning import (Bases, Runner, resolve_walk, resolve_single, resolve_double,
                          resolve_triple, resolve_homer, resolve_error, dp_prob, sf_score_prob)
from .defense import TeamDefense
from .pitching_manager import PitchingStaff
from .probability import TUNE


@dataclass
class PAResult:
    outcome: str                 # K/BB/HBP/1B/2B/3B/HR/GO/FO/LO/DP/SF/E(실책 출루)
    scored: list = field(default_factory=list)   # 득점한 Runner들 (순서 = 홈인 순)
    outs_added: int = 0
    pitches: int = 0
    ball_type: str = ""          # GB/LD/FB ("" = 인플레이 아님)


def same_hand(batter: Player, pitcher: Player) -> bool:
    """플래툰 판정. 스위치 히터는 항상 반대 손 타석 → 같은 손 아님."""
    if batter.bats == "S":
        return False
    return batter.bats == pitcher.throws


def resolve_pa(rng, batter: Player, staff: PitchingStaff, defense: TeamDefense,
               bases: Bases, outs: int, park_hr: float = 1.0,
               park_xbh: float = 1.0) -> PAResult:
    pitcher = staff.current
    fatigue = staff.fatigue_penalty()
    tto = staff.times_through_order()
    sh = same_hand(batter, pitcher)
    batter_runner = Runner(batter, pitcher)

    probs = prob.pa_event_probs(batter, pitcher, fatigue=fatigue, tto=tto,
                                same_hand=sh, park_hr=park_hr)
    r = rng.random()
    acc = probs["HBP"]
    if r < acc:
        scored = resolve_walk(bases, batter_runner)
        return PAResult("HBP", scored, 0, prob.pitches_for(rng, "HBP"))
    acc += probs["K"]
    if r < acc:
        return PAResult("K", [], 1, prob.pitches_for(rng, "K"))
    acc += probs["BB"]
    if r < acc:
        scored = resolve_walk(bases, batter_runner)
        return PAResult("BB", scored, 0, prob.pitches_for(rng, "BB"))
    acc += probs["HR"]
    if r < acc:
        scored = resolve_homer(bases, batter_runner)
        return PAResult("HR", scored, 0, prob.pitches_for(rng, "HR"))

    # ---- 인플레이 ----
    bt = prob.ball_type(rng, batter, pitcher)
    p_hit = prob.bip_hit_prob(bt, batter, pitcher,
                              if_def_z=defense.if_def_z, of_def_z=defense.of_def_z,
                              fatigue=fatigue, tto=tto, same_hand=sh)
    npitch = prob.pitches_for(rng, "BIP")

    if rng.random() < p_hit:
        kind = prob.hit_kind(rng, bt, batter, park_xbh)
        if kind == "1B":
            scored = resolve_single(rng, bases, batter_runner, defense.of_arm_z)
        elif kind == "2B":
            scored = resolve_double(rng, bases, batter_runner, defense.of_arm_z)
        else:
            scored = resolve_triple(bases, batter_runner)
        return PAResult(kind, scored, 0, npitch, bt)

    # ---- 실책: 아웃 판정 타구가 수비 실수로 출루로 바뀜 (비자책) ----
    def_z = defense.if_def_z if bt == "GB" else defense.of_def_z
    p_err = prob.matchup(TUNE["lg"]["err"], 0.0, TUNE["sens"]["err_def"] * def_z)
    if rng.random() < p_err:
        batter_runner.earned = False
        scored = resolve_error(bases, batter_runner)
        return PAResult("E", scored, 0, npitch, bt)

    # ---- 아웃 (타구 유형별 부수 효과) ----
    if bt == "GB":
        if bases.first and outs < 2 and rng.random() < dp_prob(batter, defense.if_def_z):
            bases.slots[0] = None  # 선행주자 포스아웃 + 타자 아웃 (병살 시 득점 불인정)
            return PAResult("DP", [], 2, npitch, bt)
        scored = []
        if outs < 2:  # 이 아웃이 3아웃이 아닐 때만 주자 플레이
            lg = TUNE["lg"]
            if bases.third and rng.random() < lg["go_score3"]:
                scored.append(bases.third)
                bases.slots[2] = None
            if bases.second and bases.slots[2] is None and rng.random() < lg["go_advance"]:
                bases.slots[2] = bases.second
                bases.slots[1] = None
        return PAResult("GO", scored, 1, npitch, bt)

    if bt == "FB":
        scored = []
        if outs < 2:
            lg = TUNE["lg"]
            if bases.third and rng.random() < sf_score_prob(bases.third, defense.of_arm_z):
                scored.append(bases.third)
                bases.slots[2] = None
                return PAResult("SF", scored, 1, npitch, bt)
            if bases.second and bases.slots[2] is None and rng.random() < lg["fb_tag23"]:
                bases.slots[2] = bases.second
                bases.slots[1] = None
        return PAResult("FO", scored, 1, npitch, bt)

    return PAResult("LO", [], 1, npitch, bt)  # 라인드라이브 아웃: 주자 동결
