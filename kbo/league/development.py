"""2군·육성 시스템.

1군 경기 엔진은 ``Team.roster``만 사용한다. 2군 선수는 ``Team.minors``에 보관하며
등록일과 육성 방향에 따라 오프시즌에 소폭의 추가 성장 보너스를 받는다.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..engine.probability import TUNE, clamp, precompute_all
from ..models.player import Player
from ..models.team import Team
from .aging import BAT_W, PIT_W, ensure_talents, make_rookie, overall

ACTIVE_MIN = 20
ACTIVE_MAX = 28
TARGET_ACTIVE = 25
MIN_ACTIVE_BATTERS = 9
MIN_ACTIVE_PITCHERS = 6
INITIAL_FARM_SIZE = 5
FOCUS_OPTIONS = {
    "balanced",
    "contact", "power", "defense",
    "velocity", "control", "stuff", "stamina",
}


@dataclass
class DevelopmentReport:
    gains: list = field(default_factory=list)      # [(Team, Player, gain)]
    retired: list = field(default_factory=list)    # 예약 훅


def ensure_player_fields(player: Player) -> None:
    defaults = {
        "development_focus": "balanced",
        "minor_days": 0,
        "minor_seasons": 0,
        "dev_last_gain": 0.0,
    }
    for name, value in defaults.items():
        if not hasattr(player, name):
            setattr(player, name, value)


def _farm_positions() -> list[str]:
    return ["C", "SS", "CF", "SP", "RP"]


def ensure_farms(rng: random.Random, teams: list[Team], year: int = 1,
                 size: int = INITIAL_FARM_SIZE) -> None:
    """기존 저장 파일을 마이그레이션하고 구단별 최소 2군 인원을 채운다."""
    for team in teams:
        if not hasattr(team, "minors"):
            team.minors = []
        for player in list(team.roster) + list(team.minors):
            ensure_player_fields(player)
        existing = {p.pid for p in team.roster + team.minors}
        seq = 0
        positions = _farm_positions()
        while len(team.minors) < size:
            pos = positions[len(team.minors) % len(positions)]
            while True:
                token = f"F{year}N{seq}"
                pid = f"{team.tid}-{token}"
                seq += 1
                if pid not in existing:
                    break
            rookie = make_rookie(rng, team.tid, pos, token)
            rookie.name = f"{team.tid} 유망주 {len(team.minors) + 1}"
            rookie.development_focus = "balanced"
            team.minors.append(rookie)
            existing.add(rookie.pid)


def accrue_minor_days(teams: list[Team], days: int = 1) -> None:
    for team in teams:
        for player in team.minors:
            ensure_player_fields(player)
            player.minor_days += max(0, days)


def _rebuild_roles(team: Team) -> None:
    team.build_default_lineup()
    team.build_default_pitching()
    if team.user_managed:
        team.user_managed = True


def promote(team: Team, pid: str) -> Player:
    if len(team.roster) >= ACTIVE_MAX:
        raise ValueError(f"1군 정원은 최대 {ACTIVE_MAX}명입니다.")
    player = next((p for p in team.minors if p.pid == pid), None)
    if player is None:
        raise ValueError("2군에 없는 선수입니다.")
    team.minors.remove(player)
    team.roster.append(player)
    player.team_id = team.tid
    _rebuild_roles(team)
    return player


def demote(team: Team, pid: str) -> Player:
    player = next((p for p in team.roster if p.pid == pid), None)
    if player is None:
        raise ValueError("1군에 없는 선수입니다.")
    if len(team.roster) <= ACTIVE_MIN:
        raise ValueError(f"1군은 최소 {ACTIVE_MIN}명을 유지해야 합니다.")
    batters_after = sum(not p.is_pitcher for p in team.roster if p.pid != pid)
    pitchers_after = sum(p.is_pitcher for p in team.roster if p.pid != pid)
    if batters_after < MIN_ACTIVE_BATTERS:
        raise ValueError(f"1군 야수는 최소 {MIN_ACTIVE_BATTERS}명이 필요합니다.")
    if pitchers_after < MIN_ACTIVE_PITCHERS:
        raise ValueError(f"1군 투수는 최소 {MIN_ACTIVE_PITCHERS}명이 필요합니다.")
    team.roster.remove(player)
    team.minors.append(player)
    _rebuild_roles(team)
    return player


def set_focus(team: Team, pid: str, focus: str) -> Player:
    focus = focus.lower()
    if focus not in FOCUS_OPTIONS:
        raise ValueError("지원하지 않는 육성 방향입니다.")
    player = next((p for p in team.minors if p.pid == pid), None)
    if player is None:
        raise ValueError("육성 방향은 2군 선수에게만 지정할 수 있습니다.")
    if player.is_pitcher and focus in {"contact", "power", "defense"}:
        raise ValueError("투수에게 적용할 수 없는 육성 방향입니다.")
    if not player.is_pitcher and focus in {"velocity", "control", "stuff", "stamina"}:
        raise ValueError("야수에게 적용할 수 없는 육성 방향입니다.")
    player.development_focus = focus
    return player


def _focus_multiplier(player: Player, rating_name: str) -> float:
    focus = player.development_focus
    if focus == "balanced":
        return 0.75
    if not player.is_pitcher:
        mapping = {
            "contact": {"contact", "eye"},
            "power": {"power"},
            "defense": {"fielding", "arm", "speed"},
        }
    else:
        mapping = {
            "velocity": {"velocity"},
            "control": {"control"},
            "stuff": {"stuff", "breaking"},
            "stamina": {"stamina"},
        }
    return 1.55 if rating_name in mapping.get(focus, set()) else 0.35


def development_tick(rng: random.Random, teams: list[Team]) -> DevelopmentReport:
    """완료된 시즌의 2군 등록일을 능력치 보너스로 환산한다."""
    report = DevelopmentReport()
    all_players = [p for team in teams for p in team.roster + team.minors]
    ensure_talents(rng, all_players)
    a = TUNE["aging"]
    for team in teams:
        for player in team.minors:
            ensure_player_fields(player)
            before = overall(player)
            if player.minor_days >= 30:
                season_frac = min(1.0, player.minor_days / 144.0)
                age_mult = 1.0 if player.age <= 23 else (0.75 if player.age <= 26 else 0.35)
                talent_mult = 0.65 + 0.55 * player.tal_g
                base = season_frac * age_mult * talent_mult
                ratings = player.pit if player.is_pitcher else player.bat
                names = PIT_W if player.is_pitcher else BAT_W
                for name in names:
                    delta = base * _focus_multiplier(player, name) + rng.gauss(0.0, 0.08)
                    delta = clamp(delta, 0.0, 2.2)
                    setattr(ratings, name,
                            clamp(getattr(ratings, name) + delta,
                                  a["rating_min"], a["rating_max"]))
            after = overall(player)
            player.dev_last_gain = round(max(0.0, after - before), 2)
            if player.dev_last_gain > 0:
                report.gains.append((team, player, player.dev_last_gain))
            if player.minor_days >= 100:
                player.minor_seasons += 1
            player.minor_days = 0
    precompute_all(p for team in teams for p in team.roster + team.minors)
    report.gains.sort(key=lambda row: row[2], reverse=True)
    return report


def _make_room_for_callup(team: Team, pitcher: bool) -> Player | None:
    if len(team.roster) < ACTIVE_MAX:
        return None
    injured = [p for p in team.roster if p.is_pitcher == pitcher and p.inj_days > 0]
    if not injured:
        return None
    player = max(injured, key=lambda p: p.inj_days)
    team.roster.remove(player)
    team.minors.append(player)
    return player


def auto_cover_injuries(team: Team) -> list[dict]:
    """경기 진행이 불가능한 수준의 부상 공백만 자동 콜업한다."""
    moves = []
    needs = [
        (False, 9, "야수"),
        (True, 6, "투수"),
    ]
    for pitcher, minimum, label in needs:
        while sum(p.inj_days == 0 and p.is_pitcher == pitcher for p in team.roster) < minimum:
            candidates = [p for p in team.minors
                          if p.inj_days == 0 and p.is_pitcher == pitcher]
            if not candidates:
                break
            sent_down = _make_room_for_callup(team, pitcher)
            if len(team.roster) >= ACTIVE_MAX:
                break
            candidate = max(candidates, key=overall)
            team.minors.remove(candidate)
            team.roster.append(candidate)
            candidate.team_id = team.tid
            moves.append({
                "type": "callup", "pid": candidate.pid, "name": candidate.name,
                "group": label,
                "demoted": sent_down.name if sent_down else None,
            })
    if moves:
        _rebuild_roles(team)
    return moves


def auto_assign_active(team: Team) -> dict:
    """전체 보유 선수 중 OVR 기준 14야수·11투수를 1군으로 편성한다."""
    players = team.roster + team.minors
    batters = sorted([p for p in players if not p.is_pitcher], key=overall, reverse=True)
    pitchers = sorted([p for p in players if p.is_pitcher], key=overall, reverse=True)
    active = batters[:14] + pitchers[:11]
    # 인원이 부족한 유형은 남은 최고 선수로 25명까지 보충한다.
    chosen = {p.pid for p in active}
    rest = sorted([p for p in players if p.pid not in chosen], key=overall, reverse=True)
    active += rest[:max(0, TARGET_ACTIVE - len(active))]
    active = active[:TARGET_ACTIVE]
    active_ids = {p.pid for p in active}
    before = {p.pid for p in team.roster}
    team.roster = [p for p in players if p.pid in active_ids]
    team.minors = [p for p in players if p.pid not in active_ids]
    _rebuild_roles(team)
    return {
        "promoted": [p.name for p in team.roster if p.pid not in before],
        "demoted": [p.name for p in team.minors if p.pid in before],
    }
