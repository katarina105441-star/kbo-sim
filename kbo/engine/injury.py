"""부상 시스템 — 나이·포지션·등판부하 기반 발생 확률과 기간 분포.

매 경기일 종료 후 daily_injury_tick 호출:
  부상자는 회복 카운트다운(+결장 집계), 건강한 선수는 부상 판정.
발생 확률 가중: 나이(30세 초과 1세당 +3.5%), 포수 ×1.5,
투수는 당일 투구수 비례 가산 (선발 100구 등판일 ≈ 기본의 3.5배).
기간: 경미(60%) 2~7일 / 중간(25%) 8~20일 / 중상(12%) 21~50일 / 시즌아웃급(3%) 60~120일.
"""
from __future__ import annotations

from ..models.player import Player
from .probability import TUNE


def injury_prob(player: Player, outing_pitches: int = 0) -> float:
    inj = TUNE["injury"]
    if player.is_pitcher:
        p = inj["pit_daily"] + outing_pitches * inj["outing_coef"]
    else:
        p = inj["bat_daily"] * (inj["catcher_mult"] if player.pos == "C" else 1.0)
    return p * (1.0 + max(0, player.age - 30) * inj["age_coef"])


def roll_injury_days(rng, player: Player, outing_pitches: int = 0) -> int:
    """부상 발생 시 결장일 반환, 아니면 0."""
    if rng.random() >= injury_prob(player, outing_pitches):
        return 0
    r = rng.random()
    acc = 0.0
    for share, lo, hi in TUNE["injury"]["dur"]:
        acc += share
        if r <= acc:
            return rng.randint(lo, hi)
    return rng.randint(60, 120)


def daily_injury_tick(rng, teams, outing_pitches: dict) -> None:
    """경기일 종료 처리. outing_pitches: {pid: 당일 투구수}."""
    for t in teams:
        for p in t.roster:
            if p.inj_days > 0:
                p.missed += 1
                p.inj_days -= 1
            else:
                d = roll_injury_days(rng, p, outing_pitches.get(p.pid, 0))
                if d:
                    p.inj_days = d
