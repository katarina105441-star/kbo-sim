"""KBO 포스트시즌 — 계단식 토너먼트.

와일드카드(4위 1승 어드밴티지, 최대 2경기, 전 경기 4위 홈)
→ 준플레이오프(3위 vs WC승자, 5전3선승, 홈 2-2-1)
→ 플레이오프(2위 vs 준PO승자, 5전3선승, 홈 2-2-1)
→ 한국시리즈(1위 vs PO승자, 7전4선승, 홈 2-3-2)

단기전 특성:
- 선발은 로테이션 순번이 아니라 '휴식 3일 이상인 최고 선발'을 지정 등판
  (에이스가 중3일로 1·4·7차전에 나서는 실전 패턴이 자연 발생)
- 총력전 모드: 선발 조기 강판, 필승조 우선 투입 → 연투 페널티가 실제로 작동
- 시리즈 내 휴식일(2차전·4차전 후), 시리즈 간 2일 휴식 (로테이션 리셋 기회)
- 무승부(연장 15회+) 시 재경기, 개인 기록은 ps_bat/ps_pit로 분리 집계
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from ..models.team import Team
from ..engine.game import GameSimulator, GameResult
from ..engine.injury import daily_injury_tick
from ..engine.form import daily_form_tick
from ..engine.probability import TUNE
from .usage import PitcherUsageTracker


@dataclass
class SeriesResult:
    name: str
    upper: Team
    lower: Team
    wins_u: int
    wins_l: int
    winner: Team
    games: list = field(default_factory=list)  # (home_tid, away_tid, (a, h), tie)


@dataclass
class PostseasonResult:
    rounds: list          # list[SeriesResult]
    champion: Team


# (라운드명, 상위팀 필요승수, 하위팀 필요승수, 홈 배분 패턴)
ROUNDS = [
    ("와일드카드 결정전", 1, 2, "UU"),
    ("준플레이오프", 3, 3, "UULLU"),
    ("플레이오프", 3, 3, "UULLU"),
    ("한국시리즈", 4, 4, "UULLLUU"),
]


class PostseasonRunner:
    def __init__(self, ranked: list[Team], rng: random.Random, start_day: int = 144):
        self.ranked = ranked[:5]   # 정규시즌 순위 1~5위
        self.rng = rng
        self.day = start_day
        self.tracker = PitcherUsageTracker()
        # 팀별 마지막 실전일 (경기감각 저하 판정용) — 정규시즌 종료일로 초기화
        self.last_played = {t.tid: start_day - 1 for t in self.ranked}
        # 검증용 지표: 중3일 선발 [경기수, 승수] / 충분휴식 선발 [경기수, 승수] / 불펜 연투 등판
        self.metrics = {"short_rest": [0, 0], "normal_rest": [0, 0],
                        "relief_entries": 0, "tired_relief_entries": 0}

    # ---------- 진행 ----------
    def run(self) -> PostseasonResult:
        self._rest(4)  # 정규시즌 종료 후 휴식 (부상 회복·불펜 리셋)
        r = self.ranked
        rounds = []
        cur = None  # 아래에서 올라오는 팀
        pairs = [(r[3], r[4]), (r[2], None), (r[1], None), (r[0], None)]
        for (name, need_u, need_l, homes), (upper, lower) in zip(ROUNDS, pairs):
            lower = lower if lower is not None else cur
            sr = self._series(name, need_u, need_l, homes, upper, lower)
            rounds.append(sr)
            cur = sr.winner
            self._rest(2)  # 시리즈 간 휴식 (로테이션 리셋 기회)
        return PostseasonResult(rounds, cur)

    def _apply_rust(self, team: Team) -> None:
        """장기 실전 공백 팀의 경기감각 저하 — 음의 폼 쇼크 (시리즈 중 자연 회복)."""
        rust = TUNE["ps_rust"]
        if self.day - self.last_played[team.tid] - 1 >= rust["idle_days"]:
            for p in team.roster:
                p.form_day -= rust["shock"]

    def _series(self, name, need_u, need_l, homes, upper: Team, lower: Team) -> SeriesResult:
        self._apply_rust(upper)
        self._apply_rust(lower)
        wu = wl = 0
        gi = 0
        games = []
        while wu < need_u and wl < need_l and gi < 12:
            h_upper = homes[min(gi, len(homes) - 1)] == "U"
            home, away = (upper, lower) if h_upper else (lower, upper)
            res = self._play_game(home, away)
            games.append((home.tid, away.tid, res.score, res.tie))
            if not res.tie:  # 무승부는 재경기 (승수 무변동)
                winner = home if res.score[1] > res.score[0] else away
                if winner is upper:
                    wu += 1
                else:
                    wl += 1
            gi += 1
            if gi in (2, 4) and wu < need_u and wl < need_l:
                self._rest(1)  # 시리즈 내 이동/휴식일
        winner = upper if wu >= need_u else (lower if wl >= need_l else upper)
        return SeriesResult(name, upper, lower, wu, wl, winner, games)

    def _play_game(self, home: Team, away: Team) -> GameResult:
        day = self.day
        home.build_default_lineup()
        away.build_default_lineup()
        starters = {}
        rest_cls = {}
        for key, team in (("home", home), ("away", away)):
            sp = self._pick_starter(team)
            starters[key] = sp
            r = self.tracker.rest_of(sp, day)
            rest_cls[key] = "short_rest" if (r is not None and r <= 3) else "normal_rest"
        ctx_h, ctx_a = self.tracker.ctx(home, day), self.tracker.ctx(away, day)
        sim = GameSimulator(
            home, away, self.rng, record=True, stat_target="ps",
            allow_tie=False, max_innings=15, aggressive=True,
            home_unavailable=self.tracker.unavailable(home, day),
            away_unavailable=self.tracker.unavailable(away, day),
            home_pitcher_ctx=ctx_h, away_pitcher_ctx=ctx_a,
            home_starter=starters["home"], away_starter=starters["away"])
        res = sim.run()
        # 검증 지표 수집
        if not res.tie:
            home_won = res.score[1] > res.score[0]
            for key, won in (("home", home_won), ("away", not home_won)):
                m = self.metrics[rest_cls[key]]
                m[0] += 1
                m[1] += 1 if won else 0
        for side, ctx in (("home", ctx_h), ("away", ctx_a)):
            for st in res.stints[side][1:]:
                self.metrics["relief_entries"] += 1
                if ctx.get(st.player.pid, {}).get("pen", 0.0) > 0:
                    self.metrics["tired_relief_entries"] += 1
        self.tracker.track(res, day)
        self.last_played[home.tid] = day
        self.last_played[away.tid] = day
        outing = {st.player.pid: st.line.pitches
                  for s in ("home", "away") for st in res.stints[s]}
        daily_injury_tick(self.rng, self.ranked, outing)
        daily_form_tick(self.rng, self.ranked)
        self.day += 1
        return res

    def _pick_starter(self, team: Team):
        """휴식 3일 이상인 선발 중 최고 (단기전 지정 등판 — 에이스 중3일 재등판)."""
        day = self.day

        def rest_ok(p):
            r = self.tracker.rest_of(p, day)
            return r is None or r >= 3

        sps = [p for p in team.pitchers if p.pos == "SP" and p.inj_days == 0]
        ready = [p for p in sps if rest_ok(p)]
        if not ready:  # 선발 전원 휴식 부족: 스윙맨/불펜 (마무리 제외) 총동원
            ready = [p for p in team.pitchers
                     if p.inj_days == 0 and p.pos != "CL" and rest_ok(p)] or sps or team.pitchers
        return max(ready, key=lambda p: p.pit_overall)

    def _rest(self, n: int) -> None:
        """휴식일: 경기 없이 부상 회복·폼 변동만 진행."""
        for _ in range(n):
            for t in self.ranked:
                for p in t.roster:
                    if p.inj_days > 0:
                        p.inj_days -= 1
            daily_form_tick(self.rng, self.ranked)
            self.day += 1
