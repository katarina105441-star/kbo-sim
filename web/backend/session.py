"""게임 세션 — 상태머신 · 진행 · 오프시즌 자동 체인 · 저장/로드.

엔진 함수를 '호출만' 한다 (게임 로직 없음). 상태:
  SEASON(day/144) → (끝나면 자동) POSTSEASON → OFFSEASON 체인 → 새 시즌
MVP-1: 오프시즌은 전자동 통과, 단계별 요약 리포트만 남긴다.
"""
from __future__ import annotations
import os
import pickle
import random

from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick, overall
from kbo.league.draft import run_draft
from kbo.league.economy import init_market, offseason_finance_tick
from kbo.league.fa import run_fa_market, seed_service_years
from kbo.league.postseason import PostseasonRunner
from kbo.league.season import SeasonRunner
from kbo.league.trade import run_trades

SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "saves")
SERIES_DAYS, MONTH_DAYS = 3, 24


class GameSession:
    def __init__(self, user_tid: str, seed: int | None = None):
        self.teams = load_league()
        init_market(self.teams)
        seed_service_years(self.teams)
        self.rng = random.Random(seed)
        self.user_tid = user_tid.upper()
        self.user_team = next(t for t in self.teams if t.tid == self.user_tid)
        self.user_team.user_managed = True
        self.year = 1
        self.news: list[str] = []
        self.history: list[dict] = []          # 시즌별 {year, champion, my_rank}
        self.offseason_reports: list[dict] = []  # 직전 오프시즌 단계 요약
        self.postseason_summary: list[str] = []
        self._new_season()

    # ---------- 시즌 ----------
    def _new_season(self):
        self.season = SeasonRunner(self.teams, self.rng)
        self.season.record_watch = {self.user_tid}   # 내 경기만 관전 스트림 기록
        self.season.start(keep_results=False)
        self.results_by_day: list[list] = []   # [day][GameResult]

    def _collect_news(self, day_results):
        self.news = []
        for res in day_results:
            if self.user_tid in (res.home.tid, res.away.tid):
                a, h = res.score
                self.news.append(f"{res.away.tid} {a} : {h} {res.home.tid}"
                                 + (" (무승부)" if res.tie else ""))
                side = "home" if res.home.tid == self.user_tid else "away"
                for p, _slot, bl in res.box_bat[side]:
                    if bl.hr >= 1 or bl.h >= 3:
                        self.news.append(f"{p.name}: {bl.h}안타 {bl.hr}홈런 "
                                         f"{bl.rbi}타점")
        hurt = [p for p in self.user_team.roster if 0 < p.inj_days]
        for p in sorted(hurt, key=lambda x: -x.inj_days)[:3]:
            self.news.append(f"부상: {p.name} (잔여 {p.inj_days}일)")

    def advance(self, unit: str) -> dict:
        """진행. 시즌이 끝나면 포스트시즌+오프시즌 자동 통과 후 새 시즌."""
        days = {"day": 1, "series": SERIES_DAYS, "month": MONTH_DAYS,
                "season_end": 10 ** 6}[unit]
        played = 0
        while played < days and not self.season.finished:
            res = self.season.step_day()
            self.results_by_day.append(res)
            played += 1
        self._collect_news(self.results_by_day[-1] if self.results_by_day else [])
        if self.season.finished:
            self._season_end()
        return {"played_days": played}

    # ---------- 시즌 종료: 포스트시즌 + 오프시즌 자동 체인 ----------
    def _season_end(self):
        ranked = self.season.standings()
        my_rank = next(i for i, t in enumerate(ranked, 1)
                       if t.tid == self.user_tid)
        ps = PostseasonRunner(ranked, self.rng,
                              start_day=self.season.days_played).run()
        seed = {t.tid: i + 1 for i, t in enumerate(ranked)}
        self.postseason_summary = [
            f"{sr.name}: {sr.upper.name}({seed[sr.upper.tid]}위) {sr.wins_u}"
            f" - {sr.wins_l} {sr.lower.name}({seed[sr.lower.tid]}위)"
            f" → {sr.winner.name}" for sr in ps.rounds]
        self.postseason_summary.append(
            f"🏆 {ps.champion.name} 한국시리즈 우승 (정규 {seed[ps.champion.tid]}위)")
        self.history.append({"year": self.year, "champion": ps.champion.name,
                             "my_rank": my_rank,
                             "my_record": f"{self.user_team.wins}승 "
                                          f"{self.user_team.ties}무 "
                                          f"{self.user_team.losses}패"})
        self._offseason(ranked)
        self.year += 1
        self._new_season()

    def _offseason(self, standings):
        y, rep = self.year, []
        my = self.user_tid

        aging = offseason_tick(self.rng, self.teams, year=y, draft_mode=True)
        rep.append({"stage": "에이징/은퇴", "items": [
            f"{t.tid} {p.name}({p.age}세) 은퇴" for t, p in aging.retired]})

        tr = run_trades(self.rng, self.teams, standings, year=y)
        rep.append({"stage": "트레이드", "items": [
            f"{d.reb_tid} {d.veteran.name}({d.veteran.age}세 {d.veteran.pos}) ↔ "
            f"{d.win_tid} {d.prospects[0].name}"
            + (f"+지명권{[pk.round for pk in d.picks]}R" if d.picks else "")
            for d in tr.trades] or ["성사된 트레이드 없음"]})

        fa = run_fa_market(self.rng, self.teams, standings, year=y)
        moved = fa.moved
        rep.append({"stage": "FA", "items": [
            f"{m.player.name}({m.player.age}세 {m.grade}등급) "
            f"{m.from_tid}→{m.to_tid} (AAV {m.aav}억)" for m in moved]
            + [f"잔류 {len(fa.signings) - len(moved)}명 / 자격 {fa.declared}명"]})

        picks = run_draft(self.rng, self.teams, standings, year=y)
        mine = [pk for pk in picks if pk.tid == my]
        rep.append({"stage": "드래프트", "items": [
            f"{pk.round}R {pk.player.name}({pk.player.age}세 {pk.player.pos})"
            for pk in mine] or ["우리 팀 지명 없음 (로스터 충원 불필요)"]})

        fin = offseason_finance_tick(self.rng, self.teams, year=y)
        rep.append({"stage": "재정", "items": [
            f"경쟁균형세 캡 {fin.cap:.0f}억",
            f"우리 예산 {self.user_team.budget:.0f}억"]
            + ([f"캡 초과 제재: {', '.join(t for t, _, _ in fin.tax_payers)}"]
               if fin.tax_payers else [])})
        self.offseason_reports = rep

    # ---------- 저장/로드 ----------
    def save(self, name: str = "save") -> str:
        os.makedirs(SAVE_DIR, exist_ok=True)
        path = os.path.join(SAVE_DIR, f"{name}.pkl")
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return path

    @staticmethod
    def load(name: str = "save") -> "GameSession":
        with open(os.path.join(SAVE_DIR, f"{name}.pkl"), "rb") as f:
            return pickle.load(f)
