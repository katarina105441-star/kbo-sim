"""주루 — 진루/도루/병살/희생플라이 판정.

베이스 상태는 [1루, 2루, 3루]의 Runner 리스트.
Runner는 (선수, 책임투수)를 기억한다 → 자책점을 출루시킨 투수에게 정확히 귀속.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ..models.player import Player
from .probability import TUNE, sigmoid, logit


@dataclass
class Runner:
    player: Player
    resp_pitcher: Player   # 이 주자를 출루시킨 투수 (자책 귀속)
    earned: bool = True    # False = 실책 출루 → 득점 시 비자책


class Bases:
    def __init__(self):
        self.slots: list[Optional[Runner]] = [None, None, None]  # 1루, 2루, 3루

    def clear(self):
        self.slots = [None, None, None]

    @property
    def first(self):
        return self.slots[0]

    @property
    def second(self):
        return self.slots[1]

    @property
    def third(self):
        return self.slots[2]

    def occupied_count(self) -> int:
        return sum(1 for s in self.slots if s)


def _adv(base: float, run_z_shift: float, arm_z_shift: float) -> float:
    return sigmoid(logit(base) + run_z_shift + arm_z_shift)


def steal_attempt_prob(runner: Runner) -> float:
    st = TUNE["steal"]
    zs = runner.player.shifts["z_spd"]
    if zs <= 0:
        return 0.0
    return min(st["cap"], st["base"] + st["coef"] * (zs ** 1.5))


def steal_success_prob(runner: Runner, c_arm_z: float) -> float:
    s = TUNE["sens"]
    return _adv(TUNE["lg"]["sb_success"],
                runner.player.shifts["run"], s["c_arm"] * c_arm_z)


def resolve_walk(bases: Bases, batter_runner: Runner) -> list[Runner]:
    """볼넷/사구: 밀어내기 진루. 득점 주자 리스트 반환."""
    scored = []
    if bases.first:
        if bases.second:
            if bases.third:
                scored.append(bases.third)
            bases.slots[2] = bases.second
        bases.slots[1] = bases.first
    bases.slots[0] = batter_runner
    return scored


def resolve_single(rng, bases: Bases, batter_runner: Runner, of_arm_z: float) -> list[Runner]:
    lg, s = TUNE["lg"], TUNE["sens"]
    scored = []
    if bases.third:
        scored.append(bases.third)
        bases.slots[2] = None
    if bases.second:
        r2 = bases.second
        bases.slots[1] = None
        if rng.random() < _adv(lg["adv_2h_single"], r2.player.shifts["run"], s["of_arm"] * of_arm_z):
            scored.append(r2)
        else:
            bases.slots[2] = r2
    if bases.first:
        r1 = bases.first
        bases.slots[0] = None
        if bases.slots[2] is None and rng.random() < _adv(
                lg["adv_13_single"], r1.player.shifts["run"], s["of_arm"] * of_arm_z * 0.7):
            bases.slots[2] = r1
        else:
            bases.slots[1] = r1
    bases.slots[0] = batter_runner
    return scored


def resolve_double(rng, bases: Bases, batter_runner: Runner, of_arm_z: float) -> list[Runner]:
    lg, s = TUNE["lg"], TUNE["sens"]
    scored = []
    if bases.third:
        scored.append(bases.third)
        bases.slots[2] = None
    if bases.second:
        scored.append(bases.second)
        bases.slots[1] = None
    if bases.first:
        r1 = bases.first
        bases.slots[0] = None
        if rng.random() < _adv(lg["adv_1h_double"], r1.player.shifts["run"], s["of_arm"] * of_arm_z):
            scored.append(r1)
        else:
            bases.slots[2] = r1
    bases.slots[1] = batter_runner
    return scored


def resolve_triple(bases: Bases, batter_runner: Runner) -> list[Runner]:
    scored = [r for r in bases.slots if r]
    bases.clear()
    bases.slots[2] = batter_runner
    return scored


def resolve_error(bases: Bases, batter_runner: Runner) -> list[Runner]:
    """실책 출루: 타자 1루, 전 주자 한 베이스씩 진루. (batter_runner.earned=False로 호출)"""
    scored = []
    if bases.third:
        scored.append(bases.third)
        bases.slots[2] = None
    if bases.second:
        bases.slots[2] = bases.second
        bases.slots[1] = None
    if bases.first:
        bases.slots[1] = bases.first
        bases.slots[0] = None
    bases.slots[0] = batter_runner
    return scored


def resolve_homer(bases: Bases, batter_runner: Runner) -> list[Runner]:
    scored = [r for r in bases.slots if r]
    scored.append(batter_runner)
    bases.clear()
    return scored


def dp_prob(batter: Player, if_def_z: float) -> float:
    s = TUNE["sens"]
    return sigmoid(logit(TUNE["lg"]["dp_rate"]) + batter.shifts["dp"] + s["dp_def"] * if_def_z)


def sf_score_prob(runner: Runner, of_arm_z: float) -> float:
    s = TUNE["sens"]
    return _adv(TUNE["lg"]["sf_deep"], runner.player.shifts["run"], s["of_arm"] * of_arm_z)
