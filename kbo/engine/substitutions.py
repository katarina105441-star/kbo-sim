"""경기 중 야수 교체 상태.

시즌용 ``Team.lineup``은 건드리지 않고, 경기 내부 활성 라인업과 사용 선수 이력을
별도로 유지한다. 대타·대주자·대수비로 한 번 빠진 선수는 재출전할 수 없다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.player import Player
from ..models.stats import BattingLine
from ..models.team import Team
from .baserunning import Bases


@dataclass
class Substitution:
    kind: str
    side: str
    out_player: Player
    in_player: Player
    order: int
    slot: str
    base: int | None = None


class SubstitutionManager:
    def __init__(self, home: Team, away: Team, box: dict[str, dict[str, BattingLine]]):
        self.teams = {"home": home, "away": away}
        self.active: dict[str, list[tuple[Player, str]]] = {
            "home": list(home.lineup),
            "away": list(away.lineup),
        }
        self.used: dict[str, set[str]] = {
            side: {p.pid for p, _ in lineup}
            for side, lineup in self.active.items()
        }
        self.players: dict[str, dict[str, Player]] = {
            side: {p.pid: p for p, _ in lineup}
            for side, lineup in self.active.items()
        }
        self.entries: dict[str, list[tuple[Player, str]]] = {
            side: list(lineup) for side, lineup in self.active.items()
        }
        self.box = box
        self.history: list[Substitution] = []

    def lineup(self, side: str) -> list[tuple[Player, str]]:
        return self.active[side]

    def bench(self, side: str) -> list[Player]:
        team = self.teams[side]
        return sorted(
            [p for p in team.batters
             if p.inj_days == 0 and p.pid not in self.used[side]],
            key=lambda p: p.bat_overall,
            reverse=True,
        )

    def _candidate(self, side: str, pid: str) -> Player:
        team = self.teams[side]
        player = next((p for p in team.roster if p.pid == pid), None)
        if player is None:
            raise ValueError("해당 팀 로스터에 없는 선수입니다.")
        if player.is_pitcher:
            raise ValueError("투수는 야수 교체 선수로 사용할 수 없습니다.")
        if player.inj_days > 0:
            raise ValueError("부상 선수는 교체 출전할 수 없습니다.")
        if player.pid in self.used[side]:
            raise ValueError("이미 출전했거나 교체된 선수는 재출전할 수 없습니다.")
        return player

    def _enter(self, side: str, player: Player, slot: str) -> None:
        self.used[side].add(player.pid)
        self.players[side][player.pid] = player
        self.box[side][player.pid] = BattingLine()
        self.entries[side].append((player, slot))

    def _replace_order(self, side: str, order_idx: int, player: Player) -> tuple[Player, str]:
        if not 0 <= order_idx < 9:
            raise ValueError("타순 번호가 올바르지 않습니다.")
        old, slot = self.active[side][order_idx]
        self.active[side][order_idx] = (player, slot)
        self._enter(side, player, slot)
        return old, slot

    def pinch_hitter(self, side: str, order_idx: int, pid: str) -> Substitution:
        player = self._candidate(side, pid)
        old, slot = self._replace_order(side, order_idx, player)
        sub = Substitution("pinch_hitter", side, old, player, order_idx + 1, slot)
        self.history.append(sub)
        return sub

    def pinch_runner(self, side: str, bases: Bases, base: int, pid: str) -> Substitution:
        if base not in (1, 2, 3):
            raise ValueError("주자 베이스는 1, 2, 3 중 하나여야 합니다.")
        runner = bases.slots[base - 1]
        if runner is None:
            raise ValueError("해당 베이스에 주자가 없습니다.")
        player = self._candidate(side, pid)
        order_idx = next((i for i, (p, _) in enumerate(self.active[side])
                          if p.pid == runner.player.pid), None)
        if order_idx is None:
            raise ValueError("주자의 타순 위치를 찾을 수 없습니다.")
        old, slot = self._replace_order(side, order_idx, player)
        runner.player = player
        sub = Substitution("pinch_runner", side, old, player, order_idx + 1, slot, base)
        self.history.append(sub)
        return sub

    def defensive(self, side: str, out_pid: str, in_pid: str) -> Substitution:
        order_idx = next((i for i, (p, _) in enumerate(self.active[side])
                          if p.pid == out_pid), None)
        if order_idx is None:
            raise ValueError("현재 라인업에 없는 선수입니다.")
        old, slot = self.active[side][order_idx]
        if slot == "DH":
            raise ValueError("지명타자는 대수비 대상으로 지정할 수 없습니다.")
        player = self._candidate(side, in_pid)
        if player.pos != slot:
            raise ValueError(f"{slot} 수비에는 주 포지션이 {slot}인 선수만 투입할 수 있습니다.")
        self.active[side][order_idx] = (player, slot)
        self._enter(side, player, slot)
        sub = Substitution("defensive", side, old, player, order_idx + 1, slot)
        self.history.append(sub)
        return sub

    def participant_entries(self, side: str) -> list[tuple[Player, str]]:
        return self.entries[side]

    def participant_players(self, side: str) -> list[Player]:
        return list(self.players[side].values())

    def state(self, side: str, bases: Bases | None = None) -> dict:
        bench = [
            {"pid": p.pid, "name": p.name, "pos": p.pos,
             "ovr": round(p.bat_overall, 1), "speed": p.bat.speed,
             "fielding": p.bat.fielding}
            for p in self.bench(side)
        ]
        lineup = [
            {"order": i + 1, "pid": p.pid, "name": p.name, "slot": slot,
             "pos": p.pos, "bats": p.bats}
            for i, (p, slot) in enumerate(self.active[side])
        ]
        runners = []
        if bases is not None:
            runners = [
                {"base": i + 1, "pid": rn.player.pid, "name": rn.player.name}
                for i, rn in enumerate(bases.slots) if rn is not None
            ]
        return {"lineup": lineup, "bench": bench, "runners": runners}
