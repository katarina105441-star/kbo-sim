"""사용자가 직접 운영하는 경기 한 개에 야수 교체 기능을 활성화한다.

일반 ``GameSimulator`` 클래스는 변경하지 않는다. 대상 인스턴스만 동일 메모리 구조의
``ManagedGameSimulator``로 전환하므로 일반 시즌·콘솔 경기의 경로와 성능은 그대로이며,
진행 중 경기의 pickle 저장·복원도 클래스 수준 메서드로 안전하게 처리된다.
"""
from __future__ import annotations

from contextlib import contextmanager

from .defense import compute_defense
from .game import GameSimulator
from .substitutions import SubstitutionManager


def _ensure_substitutions(sim) -> None:
    if hasattr(sim, "subs"):
        return
    sim.subs = SubstitutionManager(sim.home, sim.away, sim.box)
    sim.defense = {
        "home": compute_defense(sim.home, sim.subs.lineup("home")),
        "away": compute_defense(sim.away, sim.subs.lineup("away")),
    }


@contextmanager
def _active_lineups(sim):
    _ensure_substitutions(sim)
    saved_home = sim.home.lineup
    saved_away = sim.away.lineup
    sim.home.lineup = sim.subs.lineup("home")
    sim.away.lineup = sim.subs.lineup("away")
    try:
        yield
    finally:
        sim.home.lineup = saved_home
        sim.away.lineup = saved_away


class ManagedGameSimulator(GameSimulator):
    """대타·대주자·대수비가 가능한 실시간 운영 경기."""

    def _begin_half(self):
        with _active_lineups(self):
            super()._begin_half()
        self.defense[self.fld] = compute_defense(
            self._team(self.fld), self.subs.lineup(self.fld))

    def state(self):
        with _active_lineups(self):
            payload = super().state()
        if not self.started or self.done:
            payload["batting_substitutions"] = None
            payload["fielding_substitutions"] = None
            return payload
        payload["batting_substitutions"] = self.subs.state(self.side, self.bases)
        payload["fielding_substitutions"] = self.subs.state(self.fld)
        return payload

    def step_pa(self, include_state: bool = True):
        with _active_lineups(self):
            return super().step_pa(include_state=include_state)

    def _finish(self, innings: int):
        with _active_lineups(self):
            result = super()._finish(innings)
        if self.record:
            for side in ("home", "away"):
                active = {p.pid for p, _ in self.subs.lineup(side)}
                for p in self.subs.participant_players(side):
                    if p.pid not in active:
                        getattr(p, self.stat_target + "_bat").add(self.box[side][p.pid])
        result.box_bat = {
            side: [(p, slot, self.box[side][p.pid])
                   for p, slot in self.subs.participant_entries(side)]
            for side in ("away", "home")
        }
        return result

    def _emit_substitution(self, sub) -> None:
        kind_ko = {"pinch_hitter": "대타", "pinch_runner": "대주자",
                   "defensive": "대수비"}[sub.kind]
        text = (f"{self.inning}회{self.half_ko} {kind_ko}: "
                f"{sub.out_player.name} → {sub.in_player.name}")
        if sub.base:
            text += f" ({sub.base}루)"
        self._ev(text)
        if self.record_struct:
            self._sev({"t": "substitution", "kind": sub.kind,
                       "inning": self.inning, "half": self.half_ko,
                       "team": self._team(sub.side).tid,
                       "order": sub.order, "slot": sub.slot, "base": sub.base,
                       "out": {"pid": sub.out_player.pid,
                               "name": sub.out_player.name},
                       "in": {"pid": sub.in_player.pid,
                              "name": sub.in_player.name}})

    def force_pinch_hitter(self, side: str, player_pid: str) -> dict:
        self.start()
        _ensure_substitutions(self)
        if self.done:
            raise ValueError("이미 종료된 경기입니다.")
        if not self.at_decision:
            raise ValueError("대타는 다음 타석 시작 전에만 투입할 수 있습니다.")
        if side != self.side:
            raise ValueError("현재 공격 중인 팀만 대타를 투입할 수 있습니다.")
        sub = self.subs.pinch_hitter(side, self.bo[side] % 9, player_pid)
        self._emit_substitution(sub)
        return self.state()

    def force_pinch_runner(self, side: str, base: int, player_pid: str) -> dict:
        self.start()
        _ensure_substitutions(self)
        if self.done:
            raise ValueError("이미 종료된 경기입니다.")
        if not self.at_decision:
            raise ValueError("대주자는 다음 타석 시작 전에만 투입할 수 있습니다.")
        if side != self.side:
            raise ValueError("현재 공격 중인 팀만 대주자를 투입할 수 있습니다.")
        sub = self.subs.pinch_runner(side, self.bases, base, player_pid)
        self._emit_substitution(sub)
        return self.state()

    def force_defensive_sub(self, side: str, out_pid: str, in_pid: str) -> dict:
        self.start()
        _ensure_substitutions(self)
        if self.done:
            raise ValueError("이미 종료된 경기입니다.")
        if not self.at_decision:
            raise ValueError("대수비는 다음 타석 시작 전에만 투입할 수 있습니다.")
        if side != self.fld:
            raise ValueError("현재 수비 중인 팀만 대수비를 투입할 수 있습니다.")
        sub = self.subs.defensive(side, out_pid, in_pid)
        self.defense[side] = compute_defense(
            self._team(side), self.subs.lineup(side))
        self._emit_substitution(sub)
        return self.state()


def enable_substitutions(sim: GameSimulator) -> ManagedGameSimulator:
    """실시간 운영 대상 경기 인스턴스를 교체 가능 경기로 전환한다."""
    if not isinstance(sim, ManagedGameSimulator):
        sim.__class__ = ManagedGameSimulator
    _ensure_substitutions(sim)
    return sim
