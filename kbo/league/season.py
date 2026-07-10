"""시즌 러너 — 144경기 리그를 굴리고 순위/리그 집계를 낸다.

부상(백업 자동 대체)·컨디션(폼)·등판간격(선발 휴식/불펜 연투)이 매일 반영된다.
"""
from __future__ import annotations
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional

from ..models.stats import BattingLine, PitchingLine
from ..models.team import Team
from ..engine.game import GameSimulator, GameResult
from ..engine.injury import daily_injury_tick
from ..engine.form import draw_season_form, daily_form_tick
from .schedule import make_schedule
from .usage import PitcherUsageTracker


@dataclass
class LeagueTotals:
    bat: BattingLine = field(default_factory=BattingLine)
    pit: PitchingLine = field(default_factory=PitchingLine)
    games: int = 0

    @property
    def r_per_game(self) -> float:  # 팀당 경기당 득점
        return self.bat.r / (self.games * 2) if self.games else 0.0

    @property
    def hr_per_game(self) -> float:  # 팀당 경기당 홈런
        return self.bat.hr / (self.games * 2) if self.games else 0.0

    @property
    def sb_pct(self) -> float:
        att = self.bat.sb + self.bat.cs
        return self.bat.sb / att if att else 0.0


@dataclass
class PendingDay:
    """실시간 사용자 경기 때문에 정산을 보류한 하루 상태."""
    day: int
    day_seed: Optional[int]
    results: list[Optional[GameResult]]
    outing: dict[str, int] = field(default_factory=dict)
    managed_idx: Optional[int] = None
    managed_sim: Optional[GameSimulator] = None
    completed: bool = False


def _stable_seed(*parts: object) -> int:
    """프로세스와 무관한 결정론적 128-bit 시드.

    Python ``hash()``는 프로세스마다 salt가 달라지므로 격리 모드에 사용할 수 없다.
    길이 prefix를 넣어 ("ab", "c")와 ("a", "bc")도 구분한다.
    """
    h = hashlib.blake2b(digest_size=16, person=b"kbo-isolate-v1")
    for part in parts:
        raw = str(part).encode("utf-8")
        h.update(len(raw).to_bytes(4, "big"))
        h.update(raw)
    return int.from_bytes(h.digest(), "big")


class SeasonRunner:
    def __init__(self, teams: list[Team], rng: random.Random,
                 isolated: bool = False):
        self.teams = teams
        self.rng = rng
        self.isolated = isolated
        # 공유 모드는 단 한 번의 추가 draw도 하지 않는다. 격리 모드만 독립 우주를
        # 위한 root를 소비하고, 이후 모든 일/경기/팀 스트림은 root에서 파생한다.
        self._isolation_root = rng.getrandbits(128) if isolated else None
        self.schedule = make_schedule(len(teams))
        self.results: list[GameResult] = []
        self.tracker = PitcherUsageTracker()
        self.day = 0                  # 진행 위치 (step_day 훅)
        self.keep_results = False
        self.pending_day: Optional[PendingDay] = None
        # 관전 스트림 기록 대상 팀 tid 집합 (기록은 순수 관측 — 결과 무영향)
        self.record_watch: set[str] = set()

    @property
    def days_played(self) -> int:
        return len(self.schedule)

    def start(self, keep_results: bool = False) -> None:
        """시즌 준비 (UI 훅: step_day 반복 진행의 시작점)."""
        self.day = 0
        self.keep_results = keep_results
        self.pending_day = None
        for t in self.teams:
            t.reset_season()
            t.refresh_lineup()
            if not (t.user_managed and t.rotation):
                t.build_default_pitching()
        if self.isolated:
            for t in self.teams:
                draw_season_form(
                    random.Random(_stable_seed(self._isolation_root,
                                               "season-form", t.tid)),
                    [t])
        else:
            draw_season_form(self.rng, self.teams)  # 기존 공유 스트림 그대로

    @property
    def finished(self) -> bool:
        return self.day >= len(self.schedule)

    def _game_rng(self, day_seed, game_idx: int, home: Team, away: Team):
        if not self.isolated:
            return self.rng
        return random.Random(_stable_seed(
            day_seed, "game", game_idx, home.tid, away.tid))

    def _make_game(self, game_idx: int, hi: int, ai: int, day_seed) -> GameSimulator:
        home, away = self.teams[hi], self.teams[ai]
        home.refresh_lineup()  # 부상 반영 라인업 재구성 (유저 팀은 타순 유지)
        away.refresh_lineup()
        return GameSimulator(
            home, away, self._game_rng(day_seed, game_idx, home, away),
            home_unavailable=self.tracker.unavailable(home, self.day),
            away_unavailable=self.tracker.unavailable(away, self.day),
            home_pitcher_ctx=self.tracker.ctx(home, self.day),
            away_pitcher_ctx=self.tracker.ctx(away, self.day),
            record_struct=(home.tid in self.record_watch
                           or away.tid in self.record_watch))

    def _track_result(self, ctx: PendingDay, res: GameResult) -> None:
        self.tracker.track(res, self.day)
        for side in ("home", "away"):
            for st in res.stints[side]:
                ctx.outing[st.player.pid] = (
                    ctx.outing.get(st.player.pid, 0) + st.line.pitches)

    def begin_day(self, managed_tid: str | None = None) -> PendingDay:
        """하루를 시작한다.

        ``managed_tid``가 있으면 그 팀 경기만 상태머신을 시작한 채 보류하고,
        나머지 경기는 즉시 완료한다. 날짜·부상·폼 정산은 ``complete_day``까지
        진행되지 않는다.
        """
        if self.pending_day is not None:
            raise RuntimeError("이미 진행 중인 날짜가 있습니다.")
        if self.finished:
            raise RuntimeError("시즌이 이미 종료되었습니다.")
        managed_tid = managed_tid.upper() if managed_tid else None
        games = self.schedule[self.day]
        day_seed = (_stable_seed(self._isolation_root, "day", self.day)
                    if self.isolated else None)
        ctx = PendingDay(self.day, day_seed, [None] * len(games))

        for game_idx, (hi, ai) in enumerate(games):
            home, away = self.teams[hi], self.teams[ai]
            sim = self._make_game(game_idx, hi, ai, day_seed)
            if managed_tid and managed_tid in (home.tid, away.tid):
                if ctx.managed_sim is not None:
                    raise RuntimeError("관리 대상 팀 경기가 하루에 두 번 배정되었습니다.")
                ctx.managed_idx = game_idx
                ctx.managed_sim = sim
                sim.start()
                continue
            res = sim.run()
            ctx.results[game_idx] = res
            self._track_result(ctx, res)

        if managed_tid and ctx.managed_sim is None:
            raise ValueError(f"오늘 일정에 관리 대상 팀이 없습니다: {managed_tid}")
        self.pending_day = ctx
        return ctx

    def complete_day(self) -> list[GameResult]:
        """보류된 사용자 경기와 일일 부상·폼 정산을 정확히 한 번 완료한다."""
        ctx = self.pending_day
        if ctx is None:
            raise RuntimeError("진행 중인 날짜가 없습니다.")
        if ctx.completed:
            raise RuntimeError("이미 정산된 날짜입니다.")
        if ctx.managed_sim is not None:
            if not ctx.managed_sim.done:
                raise RuntimeError("관리 경기가 아직 종료되지 않았습니다.")
            res = ctx.managed_sim.result
            ctx.results[ctx.managed_idx] = res
            self._track_result(ctx, res)

        if any(res is None for res in ctx.results):
            raise RuntimeError("완료되지 않은 경기가 남아 있습니다.")

        if self.isolated:
            # 팀별, 시스템별 독립 스트림. 한 팀의 부상 발생으로 추가 난수가
            # 소비돼도 다른 팀이나 같은 팀의 폼 스트림은 이동하지 않는다.
            for t in self.teams:
                daily_injury_tick(
                    random.Random(_stable_seed(ctx.day_seed, "injury", t.tid)),
                    [t], ctx.outing)
                daily_form_tick(
                    random.Random(_stable_seed(ctx.day_seed, "form", t.tid)), [t])
        else:
            daily_injury_tick(self.rng, self.teams, ctx.outing)
            daily_form_tick(self.rng, self.teams)

        results = list(ctx.results)
        if self.keep_results:
            self.results.extend(results)
        ctx.completed = True
        self.pending_day = None
        self.day += 1
        return results

    def complete_managed_game(self) -> list[GameResult]:
        """실시간 경기 종료 후 호출하는 명시적 별칭."""
        return self.complete_day()

    def step_day(self) -> list[GameResult]:
        """기존 자동 진행 API. begin/complete를 연속 호출해 종전 결과를 유지한다."""
        self.begin_day()
        return self.complete_day()

    def run(self, keep_results: bool = False) -> None:
        self.start(keep_results)
        while not self.finished:
            self.step_day()

    def standings(self) -> list[Team]:
        return sorted(self.teams, key=lambda t: (t.pct, t.wins), reverse=True)

    def league_totals(self) -> LeagueTotals:
        tot = LeagueTotals()
        for t in self.teams:
            for p in t.roster:
                tot.bat.add(p.season_bat)
                tot.pit.add(p.season_pit)
        tot.games = sum(t.wins + t.losses + t.ties for t in self.teams) // 2
        return tot
