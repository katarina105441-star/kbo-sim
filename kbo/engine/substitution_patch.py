"""기존 ``GameSimulator``에 경기 중 야수 교체 기능을 부착한다.

원본 자동 경기 로직을 복제하지 않고, 각 호출 동안만 Team.lineup을 경기 내부 활성
라인업으로 교체했다가 복원한다. 따라서 시즌 라인업은 오염되지 않고 기존 RNG 소비와
자동 경기 결과도 교체를 하지 않는 한 그대로 유지된다.
"""
from __future__ import annotations

from contextlib import contextmanager

from .defense import compute_defense
from .game import GameSimulator
from .substitutions import SubstitutionManager


@contextmanager
def _active_lineups(sim):
    saved_home = sim.home.lineup
    saved_away = sim.away.lineup
    sim.home.lineup = sim.subs.lineup("home")
    sim.away.lineup = sim.subs.lineup("away")
    try:
        yield
    finally:
        sim.home.lineup = saved_home
        sim.away.lineup = saved_away


def apply_substitution_patch() -> None:
    cls = GameSimulator
    if getattr(cls, "_substitution_patch_applied", False):
        return

    original_init = cls.__init__
    original_state = cls.state
    original_step_pa = cls.step_pa
    original_begin_half = cls._begin_half
    original_finish = cls._finish

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.subs = SubstitutionManager(self.home, self.away, self.box)
        self.defense = {
            "home": compute_defense(self.home, self.subs.lineup("home")),
            "away": compute_defense(self.away, self.subs.lineup("away")),
        }

    def patched_begin_half(self):
        with _active_lineups(self):
            original_begin_half(self)
        self.defense[self.fld] = compute_defense(
            self._team(self.fld), self.subs.lineup(self.fld))

    def patched_state(self):
        with _active_lineups(self):
            payload = original_state(self)
        if not self.started or self.done:
            payload["batting_substitutions"] = None
            payload["fielding_substitutions"] = None
            return payload
        payload["batting_substitutions"] = self.subs.state(self.side, self.bases)
        payload["fielding_substitutions"] = self.subs.state(self.fld)
        return payload

    def patched_step_pa(self, include_state: bool = True):
        with _active_lineups(self):
            return original_step_pa(self, include_state=include_state)

    def patched_finish(self, innings: int):
        with _active_lineups(self):
            result = original_finish(self, innings)
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

    def emit_substitution(self, sub) -> None:
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
        if self.done:
            raise ValueError("이미 종료된 경기입니다.")
        if not self.at_decision:
            raise ValueError("대타는 다음 타석 시작 전에만 투입할 수 있습니다.")
        if side != self.side:
            raise ValueError("현재 공격 중인 팀만 대타를 투입할 수 있습니다.")
        order_idx = self.bo[side] % 9
        sub = self.subs.pinch_hitter(side, order_idx, player_pid)
        emit_substitution(self, sub)
        return self.state()

    def force_pinch_runner(self, side: str, base: int, player_pid: str) -> dict:
        self.start()
        if self.done:
            raise ValueError("이미 종료된 경기입니다.")
        if not self.at_decision:
            raise ValueError("대주자는 다음 타석 시작 전에만 투입할 수 있습니다.")
        if side != self.side:
            raise ValueError("현재 공격 중인 팀만 대주자를 투입할 수 있습니다.")
        sub = self.subs.pinch_runner(side, self.bases, base, player_pid)
        emit_substitution(self, sub)
        return self.state()

    def force_defensive_sub(self, side: str, out_pid: str, in_pid: str) -> dict:
        self.start()
        if self.done:
            raise ValueError("이미 종료된 경기입니다.")
        if not self.at_decision:
            raise ValueError("대수비는 다음 타석 시작 전에만 투입할 수 있습니다.")
        if side != self.fld:
            raise ValueError("현재 수비 중인 팀만 대수비를 투입할 수 있습니다.")
        sub = self.subs.defensive(side, out_pid, in_pid)
        self.defense[side] = compute_defense(
            self._team(side), self.subs.lineup(side))
        emit_substitution(self, sub)
        return self.state()

    cls.__init__ = patched_init
    cls._begin_half = patched_begin_half
    cls.state = patched_state
    cls.step_pa = patched_step_pa
    cls._finish = patched_finish
    cls.force_pinch_hitter = force_pinch_hitter
    cls.force_pinch_runner = force_pinch_runner
    cls.force_defensive_sub = force_defensive_sub
    cls._emit_substitution = emit_substitution
    cls._substitution_patch_applied = True
