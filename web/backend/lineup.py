"""유저 라인업 편집 검증과 직렬화.

API는 이 모듈을 통해 Team의 기존 라인업/투수진 구조만 갱신한다. 경기 확률이나
밸런싱 값은 다루지 않는다.
"""
from __future__ import annotations

from kbo.models.team import FIELD_SLOTS, Team
from web.backend.serializers import player_brief, team_summary

LINEUP_SLOTS = FIELD_SLOTS + ["DH"]


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} 선수는 중복될 수 없습니다.")


def _players(team: Team, pids: list[str], label: str):
    by_pid = {p.pid: p for p in team.roster}
    missing = [pid for pid in pids if pid not in by_pid]
    if missing:
        raise ValueError(f"{label}에 로스터 외 선수가 있습니다: {', '.join(missing)}")
    return [by_pid[pid] for pid in pids]


def _warnings(lineup) -> list[dict]:
    warnings = []
    for player, slot in lineup:
        if player.pos != slot:
            warnings.append({
                "pid": player.pid,
                "name": player.name,
                "slot": slot,
                "primary_pos": player.pos,
                "message": f"{player.name}: 주포지션 {player.pos}, 배정 슬롯 {slot}",
            })
    return warnings


def apply_lineup(team: Team, order: list[str], slots: dict[str, str],
                 rotation: list[str], closer: str | None,
                 setup: list[str]) -> dict:
    """전체 구성을 먼저 검증한 뒤 한 번에 반영한다.

    투수 보직 정책: 로테이션 5명, 마무리 1명, 셋업 목록은 모두 상호 배타적이다.
    셋업은 불펜의 부분집합이며 0명 이상 지정할 수 있다.
    """
    if len(order) != 9:
        raise ValueError("타순은 정확히 9명이어야 합니다.")
    _unique(order, "타순")
    if set(slots) != set(LINEUP_SLOTS):
        missing = sorted(set(LINEUP_SLOTS) - set(slots))
        extra = sorted(set(slots) - set(LINEUP_SLOTS))
        raise ValueError(f"수비 슬롯은 C/1B/2B/3B/SS/LF/CF/RF/DH가 모두 필요합니다. "
                         f"누락={missing}, 초과={extra}")
    slot_pids = [slots[slot] for slot in LINEUP_SLOTS]
    _unique(slot_pids, "수비 슬롯")
    if set(order) != set(slot_pids):
        raise ValueError("타순 9명과 수비 슬롯 9명은 같은 선수여야 합니다.")

    batters = _players(team, order, "타순")
    if any(p.is_pitcher for p in batters):
        raise ValueError("투수는 타자 라인업에 넣을 수 없습니다.")
    hurt = [p.name for p in batters if p.inj_days > 0]
    if hurt:
        raise ValueError(f"부상자는 라인업에 저장할 수 없습니다: {', '.join(hurt)}")

    if len(rotation) != 5:
        raise ValueError("선발 로테이션은 정확히 5명이어야 합니다.")
    _unique(rotation, "선발 로테이션")
    _unique(setup, "셋업")
    if closer is None:
        raise ValueError("마무리 투수를 1명 지정해야 합니다.")
    pitcher_pids = rotation + [closer] + setup
    pitchers = _players(team, pitcher_pids, "투수진")
    if any(not p.is_pitcher for p in pitchers):
        raise ValueError("투수진에는 투수만 지정할 수 있습니다.")
    hurt_pitchers = [p.name for p in pitchers if p.inj_days > 0]
    if hurt_pitchers:
        raise ValueError(f"부상자는 투수진에 저장할 수 없습니다: "
                         f"{', '.join(hurt_pitchers)}")
    role_pids = set(rotation)
    if closer in role_pids or role_pids.intersection(setup) or closer in setup:
        raise ValueError("로테이션·마무리·셋업 투수는 서로 겹칠 수 없습니다.")

    by_pid = {p.pid: p for p in team.roster}
    slot_by_pid = {pid: slot for slot, pid in slots.items()}
    new_lineup = [(by_pid[pid], slot_by_pid[pid]) for pid in order]
    new_rotation = [by_pid[pid] for pid in rotation]
    new_closer = by_pid[closer]
    new_setup = [by_pid[pid] for pid in setup]
    new_bullpen = sorted(
        [p for p in team.pitchers
         if p.pid not in set(rotation) and p.pid != closer],
        key=lambda p: p.pit_overall, reverse=True)

    next_starter_pid = None
    if team.rotation:
        next_starter_pid = team.rotation[
            team.rot_idx % len(team.rotation)
        ].pid

    team.lineup = new_lineup
    team.rotation = new_rotation
    team.closer = new_closer
    team.setup = new_setup
    team.bullpen = new_bullpen
    team.rot_idx = next(
        (i for i, pitcher in enumerate(new_rotation)
         if pitcher.pid == next_starter_pid),
        0,
    )
    team.user_managed = True
    return lineup_payload(team, refresh=False)


def ai_recommend(team: Team) -> dict:
    team.build_default_lineup()
    team.build_default_pitching()
    order = [p.pid for p, _ in team.lineup]
    slots = {slot: p.pid for p, slot in team.lineup}
    return apply_lineup(team, order, slots,
                        [p.pid for p in team.rotation],
                        team.closer.pid if team.closer else None,
                        [p.pid for p in team.setup])


def lineup_payload(team: Team, refresh: bool = True) -> dict:
    if refresh:
        team.refresh_lineup()
    order = [p.pid for p, _ in team.lineup]
    slots = {slot: p.pid for p, slot in team.lineup}
    return {
        "team": team_summary(team),
        "order": order,
        "slots": slots,
        "rotation": [p.pid for p in team.rotation],
        "closer": team.closer.pid if team.closer else None,
        "setup": [p.pid for p in getattr(team, "setup", [])],
        "batters": [player_brief(p) for p in team.batters],
        "pitchers": [player_brief(p) for p in team.pitchers],
        "warnings": _warnings(team.lineup),
        "policy": {
            "slots": LINEUP_SLOTS,
            "pitcher_roles_disjoint": True,
            "setup_min": 0,
        },
    }
