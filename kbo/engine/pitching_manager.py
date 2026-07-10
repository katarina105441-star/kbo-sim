"""투수 운영 — 투구수·피로 모델, 교체 AI, 승/패/세이브/홀드 판정 보조.

피로: 한계투구수(스태미나 기반)를 넘긴 비율이 로짓 페널티로 작용해
구속/제구/구위 실효치가 떨어진다 → '6회에 무너지는 선발'이 자연 발생.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..models.player import Player
from ..models.stats import PitchingLine
from .probability import TUNE


@dataclass
class PitcherStint:
    player: Player
    line: PitchingLine = field(default_factory=PitchingLine)
    entered_inning: int = 1
    entered_lead: int = 0          # 등판 시점 자기 팀 리드 (홀드/세이브 판정용)
    left_with_lead: bool = False


class PitchingStaff:
    """한 경기에서 한 팀의 투수 운영 상태."""

    def __init__(self, team, unavailable: Optional[set] = None,
                 advance_rotation: bool = True,
                 pitcher_ctx: Optional[dict] = None,
                 starter: Optional[Player] = None,
                 aggressive: bool = False):
        self.team = team
        self.unavailable = unavailable or set()
        # 등판간격 컨텍스트 {pid: {"mult": 한계투구수 배율, "pen": 입장 시 피로 페널티}}
        self.ctx = pitcher_ctx or {}
        # aggressive: 단기전 총력전 모드 (선발 일찍 교체, 필승조 우선 투입)
        self.aggressive = aggressive
        if starter is None:  # 지정 선발이 없으면 로테이션 순번
            starter = team.next_starter(advance=advance_rotation)
        self.current: Player = starter
        self.stints: list[PitcherStint] = [PitcherStint(starter)]
        self.used: set[str] = {starter.pid}
        self.batters_faced_by_current = 0

    @property
    def cur_stint(self) -> PitcherStint:
        return self.stints[-1]

    # ---------- 피로 ----------
    def _is_todays_starter(self, p: Player) -> bool:
        return p is self.stints[0].player

    def pitch_limit(self, p: Player) -> float:
        f = TUNE["fatigue"]
        # 오늘의 선발(스윙맨 땜빵 포함)은 선발 기준 한계로 이닝을 소화한다
        if p.pos == "SP" or self._is_todays_starter(p):
            base = f["sp_base"] + f["sp_per_sta"] * p.pit.stamina
            if self._is_todays_starter(p):  # 등판 간격에 따른 한계 보정
                base *= self.ctx.get(p.pid, {}).get("mult", 1.0)
            return base
        return f["rp_base"] + f["rp_per_sta"] * p.pit.stamina

    def fatigue_penalty(self) -> float:
        """현재 투수의 로짓 페널티.

        입장 피로(짧은 등판간격/연투 누적) + 당일 투구수 초과분. 상한(cap)은
        물리적 타당성 한계 — 연투 강행 폴백으로 고갈 병리가 해소돼 1.6으로 완화.
        """
        entry = self.ctx.get(self.current.pid, {}).get("pen", 0.0)
        line = self.cur_stint.line
        over = line.pitches - self.pitch_limit(self.current)
        pen = entry + max(0.0, over / 60.0) * TUNE["fatigue"]["scale"]
        return min(TUNE["fatigue"]["cap"], pen)

    def times_through_order(self) -> int:
        return self.cur_stint and (self.batters_faced_by_current // 9) + 1

    # ---------- 교체 판단 ----------
    def should_replace(self, inning: int, lead: int, outs: int, runners_on: int) -> bool:
        p = self.current
        line = self.cur_stint.line
        limit = self.pitch_limit(p)
        if p.pos == "SP" or self._is_todays_starter(p):
            grace = 8 if self.aggressive else 20
            if line.pitches >= limit + grace:
                return True
            if line.pitches >= limit and runners_on == 0:
                return True
            if inning >= 7 and line.pitches >= limit - 10:
                return True
            if self.aggressive and inning >= 6 and line.pitches >= limit - 15:
                return True  # 단기전: 6회부터 일찍 불펜 가동
            if line.er >= (5 if self.aggressive else 7):
                return True
            return False
        # 불펜
        if line.pitches >= limit + 8:
            return True
        if line.er >= (3 if self.aggressive else 4):
            return True
        return False

    def want_closer(self, inning: int, lead: int) -> bool:
        cl = self.team.closer
        return (inning >= 9 and 1 <= lead <= 3 and cl is not None
                and cl.pid not in self.used and cl.pid not in self.unavailable
                and cl.inj_days == 0 and self.current is not cl)

    def pick_reliever(self, inning: int, lead: int) -> Optional[Player]:
        cands = [p for p in self.team.bullpen
                 if p.pid not in self.used and p.pid not in self.unavailable
                 and p.inj_days == 0]
        allow_closer = inning >= 8
        if (not cands and self.team.closer and self.team.closer.pid not in self.used
                and self.team.closer.pid not in self.unavailable
                and self.team.closer.inj_days == 0):
            cands = [self.team.closer]
        if not cands:  # 불펜 고갈: 연투 강행 (휴식 규칙 무시, 부상만 제외)
            cands = [p for p in self.team.bullpen
                     if p.pid not in self.used and p.inj_days == 0]
        if not cands:
            return None
        setup_pids = {p.pid for p in getattr(self.team, "setup", [])}
        cands.sort(key=lambda p: (p.pid in setup_pids, p.pit_overall), reverse=True)
        high_leverage = self.aggressive or (abs(lead) <= 2 and inning >= 7)
        if high_leverage or allow_closer:
            return cands[0]
        # 리드가 크거나 초반이면 하위 불펜부터 소모
        return cands[len(cands) // 2] if len(cands) > 1 else cands[0]

    def bring(self, p: Player, inning: int, lead: int) -> None:
        self.cur_stint.left_with_lead = lead > 0
        self.current = p
        self.used.add(p.pid)
        self.stints.append(PitcherStint(p, entered_inning=inning, entered_lead=lead))
        self.batters_faced_by_current = 0

    def maybe_change(self, inning: int, lead: int, outs: int, runners_on: int) -> Optional[Player]:
        """PA 시작 전 호출. 교체 발생 시 새 투수 반환."""
        if self.want_closer(inning, lead):
            cl = self.team.closer
            self.bring(cl, inning, lead)
            return cl
        if self.should_replace(inning, lead, outs, runners_on):
            rp = self.pick_reliever(inning, lead)
            if rp is not None:
                self.bring(rp, inning, lead)
                return rp
        return None
