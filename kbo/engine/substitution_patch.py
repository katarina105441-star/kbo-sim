"""한 개의 ``GameSimulator`` 인스턴스에 야수 교체 기능을 부착한다.

클래스 전체를 수정하지 않고 사용자가 직접 운영하는 경기 인스턴스만 확장한다.
따라서 일반 시즌·콘솔·검증 경기의 실행 경로와 성능은 원본 그대로 유지된다.
"""
from __future__ import annotations

from contextlib import contextmanager
from types import MethodType

from .defense import compute_defense
from .game import GameSimulator
from .substitutions import SubstitutionManager

_ORIGINAL_STATE = GameSimulator.state
_ORIGINAL_STEP_PA = GameSimulator.step_pa
_ORIGINAL_BEGIN_HALF = GameSimulator._begin_half
_ORIGINAL_FINISH = GameSimulator._finish


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


def _patched_begin_half(self):
    with _active_lineups(self):
        _ORIGINAL_BEGIN_HALF(self)
    self.defense[self.fld] = compute_defense(
        self._team(self.fld), self.subs.lineup(self.fld))


def _patched_state(self):
    with _active_lineups(self):
        payload = _ORIGINAL_STATE(self)
    if not self.started or self.done:
        payload["batting_substitutions"] = None
        payload["fielding_substitutions"] = None
        return payload
    payload["batting_substitutions"] = self.subs.state(self.side, self.bases)
    payload["fielding_substitutions"] = self.subs.state(self.fld)
    return payload


def _patched_step_pa(self, include_state: bool = True):
    with _active_lineups(self):
        return _ORIGINAL_STEP_PA(self, include_state=include_state)


def _patched_finish(self, innings: int):
    with _active_lineups(self):
        result = _ORIGINAL_FINISH(self, innings)
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


def _force_pinch_hitter(self, side: str, player_pid: str) -> dict:
    self.start()
    _ensure_substitutions(self)
    if self.done:
        raise ValueError("이미 종료된 경기입니다.")
    if not self.at_decision:
        raise ValueError("대타는 다음 타석 시작 전에만 투입할 수 있습니다.")
    if side != self.side:
        raise ValueError("현재 공격 중인 팀만 대타를 투입할 수 있습니다.")
    sub = self.subs.pinch_hitter(side, self.bo[side] % 9, player_pid)
    _emit_substitution(self, sub)
    return self.state()


def _force_pinch_runner(self, side: str, base: int, player_pid: str) -> dict:
    self.start()
    _ensure_substitutions(self)
    if self.done:
        raise ValueError("이미 종료된 경기입니다.")
    if not self.at_decision:
        raise ValueError("대주자는 다음 타석 시작 전에만 투입할 수 있습니다.")
    if side != self.side:
        raise ValueError("현재 공격 중인 팀만 대주자를 투입할 수 있습니다.")
    sub = self.subs.pinch_runner(side, self.bases, base, player_pid)
    _emit_substitution(self, sub)
    return self.state()


def _force_defensive_sub(self, side: str, out_pid: str, in_pid: str) -> dict:
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
    _emit_substitution(self, sub)
    return self.state()


def enable_substitutions(sim: GameSimulator) -> GameSimulator:
    """실시간 운영 대상 경기 한 개에만 교체 기능을 활성화한다."""
    if getattr(sim, "_substitutions_enabled", False):
        _ensure_substitutions(sim)
        return sim
    _ensure_substitutions(sim)
    sim._begin_half = MethodType(_patched_begin_half, sim)
    sim.state = MethodType(_patched_state, sim)
    sim.step_pa = MethodType(_patched_step_pa, sim)
    sim._finish = MethodType(_patched_finish, sim)
    sim.force_pinch_hitter = MethodType(_force_pinch_hitter, sim)
    sim.force_pinch_runner = MethodType(_force_pinch_runner, sim)
    sim.force_defensive_sub = MethodType(_force_defensive_sub, sim)
    sim._emit_substitution = MethodType(_emit_substitution, sim)
    sim._substitutions_enabled = True
    return sim
