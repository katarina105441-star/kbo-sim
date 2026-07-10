"""시즌 러너 — 144경기 리그를 굴리고 순위/리그 집계를 낸다.

부상(백업 자동 대체)·컨디션(폼)·등판간격(선발 휴식/불펜 연투)이 매일 반영된다.
"""
from __future__ import annotations
import hashlib
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
        # 관전 스트림 기록 대상 팀 tid 집합 (기록은 순수 관측 — 결과 무영향)
        self.record_watch: set[str] = set()

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

    def step_day(self) -> list[GameResult]:
        """하루 진행 후 그날 결과 반환 (UI 진행 컨트롤 훅). run()과 동일 로직."""
        games = self.schedule[self.day]
        day_seed = (_stable_seed(self._isolation_root, "day", self.day)
                    if self.isolated else None)
        day_results: list[GameResult] = []
        outing: dict[str, int] = {}
        for game_idx, (hi, ai) in enumerate(games):
            home, away = self.teams[hi], self.teams[ai]
            home.refresh_lineup()  # 부상 반영 라인업 재구성 (유저 팀은 타순 유지)
            away.refresh_lineup()
            game_rng = self.rng
            if self.isolated:
                game_rng = random.Random(_stable_seed(
                    day_seed, "game", game_idx, home.tid, away.tid))
            sim = GameSimulator(
                home, away, game_rng,
                home_unavailable=self.tracker.unavailable(home, self.day),
                away_unavailable=self.tracker.unavailable(away, self.day),
                home_pitcher_ctx=self.tracker.ctx(home, self.day),
                away_pitcher_ctx=self.tracker.ctx(away, self.day),
                record_struct=(home.tid in self.record_watch
                               or away.tid in self.record_watch))
            res = sim.run()
            self.tracker.track(res, self.day)
            for side in ("home", "away"):
                for st in res.stints[side]:
                    outing[st.player.pid] = outing.get(st.player.pid, 0) + st.line.pitches
            day_results.append(res)
            if self.keep_results:
                self.results.append(res)
        if self.isolated:
            # 팀별, 시스템별 독립 스트림. 한 팀의 부상 발생으로 추가 난수가
            # 소비돼도 다른 팀이나 같은 팀의 폼 스트림은 이동하지 않는다.
            for t in self.teams:
                daily_injury_tick(
                    random.Random(_stable_seed(day_seed, "injury", t.tid)),
                    [t], outing)
                daily_form_tick(
                    random.Random(_stable_seed(day_seed, "form", t.tid)), [t])
        else:
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
