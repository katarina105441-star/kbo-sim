"""경기 러너 — 9이닝(+연장 12회, KBO 무승부) 풀게임을 굴려 GameResult 반환.

엔진 원칙: print 금지, 문자열은 이벤트 로그(옵션)에만. rng 주입으로 재현 가능.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from ..models.stats import BattingLine
from ..models.team import Team
from .baserunning import Bases, steal_attempt_prob, steal_success_prob
from .defense import compute_defense
from .pitching_manager import PitchingStaff, PitcherStint
from .plate_appearance import resolve_pa

OUTCOME_KO = {"K": "삼진", "BB": "볼넷", "HBP": "사구", "1B": "안타", "2B": "2루타",
              "3B": "3루타", "HR": "홈런", "GO": "땅볼 아웃", "FO": "뜬공 아웃",
              "LO": "직선타 아웃", "DP": "병살타", "SF": "희생플라이", "E": "실책 출루"}


@dataclass
class GameResult:
    away: Team
    home: Team
    line: dict                       # {"away":[...], "home":[..., None=9말 생략]}
    score: tuple                     # (away, home)
    box_bat: dict                    # {"away":[(player, slot, BattingLine)...], ...}
    stints: dict                     # {"away":[PitcherStint...], ...}
    decisions: dict                  # {"W":pid, "L":pid, "SV":pid, "HLD":[pid...]}
    tie: bool
    innings: int
    events: list = field(default_factory=list)
    struct_events: list = field(default_factory=list)   # 관전 스트림 (DESIGN_WATCH.md)


class GameSimulator:
    def __init__(self, home: Team, away: Team, rng, *, record: bool = True,
                 allow_tie: bool = True, max_innings: int = 12,
                 home_unavailable: Optional[set] = None,
                 away_unavailable: Optional[set] = None,
                 home_pitcher_ctx: Optional[dict] = None,
                 away_pitcher_ctx: Optional[dict] = None,
                 home_starter=None, away_starter=None,
                 stat_target: str = "season",  # "season" | "ps" (포스트시즌 분리 집계)
                 aggressive: bool = False,
                 record_events: bool = False,
                 record_struct: bool = False):
        self.home, self.away, self.rng = home, away, rng
        self.record, self.allow_tie, self.max_innings = record, allow_tie, max_innings
        self.stat_target = stat_target
        self.record_events = record_events
        # 구조화 이벤트 계측 (DESIGN_WATCH.md): 스냅샷 append만 — 분기·rng
        # 소비 없음 → 기록 ON/OFF가 경기 결과에 영향 없음 (테스트 가드)
        self.record_struct = record_struct
        self.struct_events: list[dict] = []
        if not home.lineup:
            home.build_default_lineup(); home.build_default_pitching()
        if not away.lineup:
            away.build_default_lineup(); away.build_default_pitching()
        # 기록 경기만 로테이션을 소모한다 (단발 시뮬은 팀 상태 불변 → 시드 재현성 보장)
        self.staff = {"home": PitchingStaff(home, home_unavailable, advance_rotation=record,
                                            pitcher_ctx=home_pitcher_ctx,
                                            starter=home_starter, aggressive=aggressive),
                      "away": PitchingStaff(away, away_unavailable, advance_rotation=record,
                                            pitcher_ctx=away_pitcher_ctx,
                                            starter=away_starter, aggressive=aggressive)}
        self.defense = {"home": compute_defense(home), "away": compute_defense(away)}
        self.box = {s: {p.pid: BattingLine() for p, _ in t.lineup}
                    for s, t in (("home", home), ("away", away))}
        self.bo = {"home": 0, "away": 0}
        self.score = {"home": 0, "away": 0}
        self.line = {"home": [], "away": []}
        self.events: list[str] = []
        self.w_cand: Optional[tuple] = None   # (side, pid)
        self.l_cand: Optional[str] = None     # pid

    # ---------- 유틸 ----------
    @staticmethod
    def _other(side: str) -> str:
        return "home" if side == "away" else "away"

    def _team(self, side: str) -> Team:
        return self.home if side == "home" else self.away

    def _ev(self, txt: str) -> None:
        if self.record_events:
            self.events.append(txt)

    def _sev(self, d: dict) -> None:
        """구조화 이벤트 append (관전 스트림). seed = 결정론 연출용."""
        d["seed"] = (len(self.struct_events) * 1000003 + 7) & 0x7FFFFFFF
        self.struct_events.append(d)

    @staticmethod
    def _bases_snap(bases: Bases) -> list:
        return [r.player.pid if r else None for r in bases.slots]

    def _stint_of(self, staff: PitchingStaff, pid: str) -> PitcherStint:
        for st in staff.stints:
            if st.player.pid == pid:
                return st
        return staff.cur_stint

    # ---------- 진행 ----------
    def run(self) -> GameResult:
        inning = 1
        while True:
            self._half(inning, "away")
            if inning >= 9 and self.score["home"] > self.score["away"]:
                self.line["home"].append(None)  # 9회말 생략 (X)
                break
            self._half(inning, "home")
            if inning >= 9 and self.score["home"] != self.score["away"]:
                break
            if inning >= self.max_innings and (self.allow_tie or inning >= 20):
                break
            inning += 1
        return self._finish(inning)

    def _half(self, inning: int, side: str) -> None:
        fld = self._other(side)
        team = self._team(side)
        staff = self.staff[fld]
        defense = self.defense[fld]
        bases = Bases()
        outs = 0
        runs_before = self.score[side]
        park = self.home.park
        half_ko = "초" if side == "away" else "말"
        unearned_rest = False  # 2사 후 실책으로 연장된 이닝 → 이후 전 득점 비자책

        while outs < 3:
            lead_def = self.score[fld] - self.score[side]
            newp = staff.maybe_change(inning, lead_def, outs, bases.occupied_count())
            if newp is not None:
                self._ev(f"{inning}회{half_ko} 투수 교체: {self._team(fld).name} {newp.name}")
                if self.record_struct:
                    self._sev({"t": "pitch_change", "inning": inning,
                               "half": half_ko, "team": self._team(fld).tid,
                               "in": {"pid": newp.pid, "name": newp.name}})

            # 도루 시도 (1루 주자, 2루 비어 있을 때)
            if bases.first and not bases.second:
                rn = bases.first
                if self.rng.random() < steal_attempt_prob(rn):
                    rbox = self.box[side][rn.player.pid]
                    if self.rng.random() < steal_success_prob(rn, defense.c_arm_z):
                        bases.slots[1], bases.slots[0] = rn, None
                        rbox.sb += 1
                        self._ev(f"{inning}회{half_ko} {rn.player.name} 2루 도루 성공")
                        steal_ok = True
                    else:
                        bases.slots[0] = None
                        outs += 1
                        rbox.cs += 1
                        staff.cur_stint.line.outs += 1
                        self._ev(f"{inning}회{half_ko} {rn.player.name} 도루 실패 ({outs}사)")
                        steal_ok = False
                    if self.record_struct:
                        self._sev({"t": "steal", "inning": inning, "half": half_ko,
                                   "outs": outs, "success": steal_ok,
                                   "runner": {"pid": rn.player.pid,
                                              "name": rn.player.name},
                                   "from": 1, "to": 2})
                    if outs >= 3:
                        break

            batter, _slot = team.lineup[self.bo[side] % 9]
            self.bo[side] += 1
            staff.batters_faced_by_current += 1
            outs_before = outs
            if self.record_struct:   # 타석 전 스냅샷 (읽기만 — 로직 무영향)
                snap = {"outs": outs, "score": [self.score["away"], self.score["home"]],
                        "bases": self._bases_snap(bases),
                        "pitcher_pitches": staff.cur_stint.line.pitches,
                        "fatigued": staff.fatigue_penalty() > 0,
                        "pitcher": staff.current,
                        "order": (self.bo[side] - 1) % 9 + 1}
            res = resolve_pa(self.rng, batter, staff, defense, bases, outs,
                             park_hr=park.hr, park_xbh=park.xbh)
            outs += res.outs_added
            self._apply(res, batter, side, fld, unearned_rest)
            if self.record_struct:
                self._sev({"t": "pa", "inning": inning, "half": half_ko,
                           "outs": snap["outs"], "score": snap["score"],
                           "batter": {"pid": batter.pid, "name": batter.name,
                                      "order": snap["order"]},
                           "pitcher": {"pid": snap["pitcher"].pid,
                                       "name": snap["pitcher"].name,
                                       "pitches": snap["pitcher_pitches"],
                                       "fatigued": snap["fatigued"]},
                           "outcome": res.outcome, "ball_type": res.ball_type,
                           "pitches": res.pitches,
                           "bases_before": snap["bases"],
                           "bases_after": self._bases_snap(bases),
                           "scored": [{"pid": r.player.pid, "name": r.player.name}
                                      for r in res.scored],
                           "outs_added": res.outs_added,
                           "rbi": len(res.scored) if res.outcome not in ("DP", "E")
                                  else 0})
            if res.outcome == "E":
                self._charge_error(fld, res.ball_type)
                if outs_before == 2:
                    unearned_rest = True
            if res.scored or res.outcome not in ("GO", "FO", "LO"):
                extra = f" ({len(res.scored)}득점)" if res.scored else ""
                self._ev(f"{inning}회{half_ko} {batter.name}: {OUTCOME_KO[res.outcome]}{extra}")
            # 끝내기
            if side == "home" and inning >= 9 and self.score["home"] > self.score["away"]:
                self._ev(f"{inning}회말 끝내기! {self.home.name} 승리")
                break
        self.line[side].append(self.score[side] - runs_before)
        if self.record_struct:
            self._sev({"t": "half_end", "inning": inning, "half": half_ko,
                       "score": [self.score["away"], self.score["home"]]})

    def _charge_error(self, fld: str, ball_type: str) -> None:
        """실책을 저지른 수비수 선정 (수비력 낮을수록 가중) 후 개인 기록 귀속."""
        slots = ("1B", "2B", "3B", "SS") if ball_type == "GB" else ("LF", "CF", "RF")
        cands = [(p, 110 - p.bat.fielding) for p, s in self._team(fld).lineup if s in slots]
        if not cands:
            return
        total = sum(w for _, w in cands)
        r = self.rng.random() * total
        for p, w in cands:
            r -= w
            if r <= 0:
                self.box[fld][p.pid].e += 1
                return

    def _apply(self, res, batter, side: str, fld: str, unearned_rest: bool) -> None:
        bl = self.box[side][batter.pid]
        cur = self.staff[fld].cur_stint.line
        oc = res.outcome
        bl.pa += 1
        if oc == "K":
            bl.ab += 1; bl.so += 1; cur.so += 1
        elif oc == "BB":
            bl.bb += 1; cur.bb += 1
        elif oc == "HBP":
            bl.hbp += 1; cur.hbp += 1
        elif oc in ("1B", "2B", "3B", "HR"):
            bl.ab += 1; bl.h += 1; cur.h += 1
            if oc == "2B":
                bl.b2 += 1
            elif oc == "3B":
                bl.b3 += 1
            elif oc == "HR":
                bl.hr += 1; cur.hr += 1
        elif oc == "E":
            bl.ab += 1  # 실책 출루: 타수 소모, 안타·출루 기록 없음
        elif oc == "DP":
            bl.ab += 1; bl.gdp += 1
        elif oc == "SF":
            bl.sf += 1
        else:  # GO/FO/LO
            bl.ab += 1
        cur.pitches += res.pitches
        cur.outs += res.outs_added

        other = self._other(side)
        for rn in res.scored:
            self.score[side] += 1
            self.box[side][rn.player.pid].r += 1
            if oc not in ("DP", "E"):
                bl.rbi += 1
            st = self._stint_of(self.staff[fld], rn.resp_pitcher.pid)
            st.line.r += 1
            if rn.earned and not unearned_rest:
                st.line.er += 1  # 실책 출루 주자·2사 후 실책 연장 득점은 비자책
            diff = self.score[side] - self.score[other]
            if diff == 1:  # 방금 리드를 잡음 → 승/패 후보 갱신
                self.w_cand = (side, self.staff[side].current.pid)
                self.l_cand = rn.resp_pitcher.pid
            elif diff == 0:
                self.w_cand = self.l_cand = None

    # ---------- 종료 처리 ----------
    def _finish(self, innings: int) -> GameResult:
        a, h = self.score["away"], self.score["home"]
        tie = a == h
        decisions = {"W": None, "L": None, "SV": None, "HLD": []}
        if not tie:
            win_side = "home" if h > a else "away"
            staff_w = self.staff[win_side]
            w_pid = self.w_cand[1] if self.w_cand and self.w_cand[0] == win_side else None
            starter = staff_w.stints[0]
            if w_pid == starter.player.pid and starter.line.outs < 15:
                relievers = staff_w.stints[1:]
                if relievers:
                    w_pid = max(relievers, key=lambda s: s.line.outs).player.pid
            if w_pid is None:  # 안전장치: 가장 오래 던진 승리팀 투수
                w_pid = max(staff_w.stints, key=lambda s: s.line.outs).player.pid
            decisions["W"] = w_pid
            decisions["L"] = self.l_cand
            last = staff_w.stints[-1]
            if (last.player.pid != w_pid and len(staff_w.stints) > 1
                    and (1 <= last.entered_lead <= 3 or last.line.outs >= 9)):
                decisions["SV"] = last.player.pid
            for st in staff_w.stints[1:-1]:
                if (st.player.pid != w_pid and 1 <= st.entered_lead <= 3
                        and st.line.outs >= 1 and st.left_with_lead):
                    decisions["HLD"].append(st.player.pid)
            # 스탯 반영
            for side in ("home", "away"):
                for st in self.staff[side].stints:
                    pid = st.player.pid
                    if pid == decisions["W"]:
                        st.line.w = 1
                    if pid == decisions["L"]:
                        st.line.l = 1
                    if pid == decisions["SV"]:
                        st.line.sv = 1
                    if pid in decisions["HLD"]:
                        st.line.hld = 1

        if self.record:
            if self.stat_target == "season":  # 팀 승패는 정규시즌만 (PS는 시리즈로 관리)
                if tie:
                    self.home.ties += 1; self.away.ties += 1
                elif h > a:
                    self.home.wins += 1; self.away.losses += 1
                else:
                    self.away.wins += 1; self.home.losses += 1
            for side, t in (("home", self.home), ("away", self.away)):
                for p, _slot in t.lineup:
                    getattr(p, self.stat_target + "_bat").add(self.box[side][p.pid])
                for i, st in enumerate(self.staff[side].stints):
                    st.line.g = 1
                    st.line.gs = 1 if i == 0 else 0
                    getattr(st.player, self.stat_target + "_pit").add(st.line)

        if self.record_struct:
            self._sev({"t": "game_end", "score": [a, h], "innings": innings,
                       "tie": tie, "decisions": decisions})
        box_bat = {s: [(p, slot, self.box[s][p.pid]) for p, slot in self._team(s).lineup]
                   for s in ("away", "home")}
        return GameResult(self.away, self.home, self.line, (a, h), box_bat,
                          {s: self.staff[s].stints for s in ("away", "home")},
                          decisions, tie, innings, self.events, self.struct_events)
