"""시즌 러너 — 144경기 리그를 굴리고 순위/리그 집계를 낸다.

부상(백업 자동 대체)·컨디션(폼)·등판간격(선발 휴식/불펜 연투)이 매일 반영된다.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

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


class SeasonRunner:
    def __init__(self, teams: list[Team], rng: random.Random):
        self.teams = teams
        self.rng = rng
        self.schedule = make_schedule(len(teams))
        self.results: list[GameResult] = []
        self.tracker = PitcherUsageTracker()
        self.day = 0                  # 진행 위치 (step_day 훅)
        self.keep_results = False

    @property
    def days_played(self) -> int:
        return len(self.schedule)

    def start(self, keep_results: bool = False) -> None:
        """시즌 준비 (UI 훅: step_day 반복 진행의 시작점)."""
        self.day = 0
        self.keep_results = keep_results
        for t in self.teams:
            t.reset_season()
            t.refresh_lineup()
            if not (t.user_managed and t.rotation):
                t.build_default_pitching()
        draw_season_form(self.rng, self.teams)  # 시즌 폼 추첨

    @property
    def finished(self) -> bool:
        return self.day >= len(self.schedule)

    def step_day(self) -> list[GameResult]:
        """하루 진행 후 그날 결과 반환 (UI 진행 컨트롤 훅). run()과 동일 로직."""
        games = self.schedule[self.day]
        day_results: list[GameResult] = []
        outing: dict[str, int] = {}
        for hi, ai in games:
            home, away = self.teams[hi], self.teams[ai]
            home.refresh_lineup()  # 부상 반영 라인업 재구성 (유저 팀은 타순 유지)
            away.refresh_lineup()
            sim = GameSimulator(
                home, away, self.rng,
                home_unavailable=self.tracker.unavailable(home, self.day),
                away_unavailable=self.tracker.unavailable(away, self.day),
                home_pitcher_ctx=self.tracker.ctx(home, self.day),
                away_pitcher_ctx=self.tracker.ctx(away, self.day))
            res = sim.run()
            self.tracker.track(res, self.day)
            for side in ("home", "away"):
                for st in res.stints[side]:
                    outing[st.player.pid] = outing.get(st.player.pid, 0) + st.line.pitches
            day_results.append(res)
            if self.keep_results:
                self.results.append(res)
        daily_injury_tick(self.rng, self.teams, outing)
        daily_form_tick(self.rng, self.teams)
        self.day += 1
        return day_results

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
