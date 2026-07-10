"""수비 집계 — 현재 라인업의 수비/송구 능력치를 팀 단위 z값으로 변환.

BABIP(안타 억제), 병살 전환, 주자 추가진루 억제에 쓰인다.
"""
from __future__ import annotations
from dataclasses import dataclass

from ..models.team import Team
from .probability import z

INFIELD = {"1B", "2B", "3B", "SS"}
OUTFIELD = {"LF", "CF", "RF"}


@dataclass
class TeamDefense:
    if_def_z: float   # 내야 수비 z (2B/SS 가중)
    of_def_z: float   # 외야 수비 z (CF 가중)
    of_arm_z: float   # 외야 송구 z
    c_arm_z: float    # 포수 송구 z


def compute_defense(team: Team, lineup=None) -> TeamDefense:
    """수비력을 계산한다.

    ``lineup``을 생략하면 시즌용 ``team.lineup``을 사용한다. 경기 중 교체가 있는
    경우에는 경기 내부 활성 라인업을 전달해 팀의 시즌 라인업을 오염시키지 않는다.
    """
    if_num = if_den = 0.0
    of_num = of_den = 0.0
    arm_num = arm_den = 0.0
    c_arm = 50.0
    for player, slot in (team.lineup if lineup is None else lineup):
        b = player.bat
        if slot in INFIELD:
            w = 1.3 if slot in {"2B", "SS"} else 1.0  # 센터라인 가중
            if_num += w * b.fielding
            if_den += w
        elif slot in OUTFIELD:
            w = 1.4 if slot == "CF" else 1.0
            of_num += w * b.fielding
            of_den += w
            arm_num += b.arm
            arm_den += 1.0
        elif slot == "C":
            c_arm = b.arm
            if_num += 0.5 * b.fielding  # 포수 수비는 내야 수비에 절반 가중
            if_den += 0.5
    return TeamDefense(
        if_def_z=z(if_num / if_den if if_den else 50.0),
        of_def_z=z(of_num / of_den if of_den else 50.0),
        of_arm_z=z(arm_num / arm_den if arm_den else 50.0),
        c_arm_z=z(c_arm),
    )
