"""웹 세션에 2군 등록일·자동 콜업·오프시즌 육성을 연결한다."""
from __future__ import annotations

import random

from kbo.league.development import (
    accrue_minor_days,
    auto_cover_injuries,
    development_tick,
    ensure_farms,
)


def _development_report(report) -> dict:
    return {
        "stage": "2군 육성",
        "items": [
            f"{team.tid} {player.name}({player.age}세 {player.pos}) "
            f"OVR +{gain:.2f} · {player.development_focus}"
            for team, player, gain in report.gains[:20]
        ] or ["이번 시즌 육성 보너스 대상 없음"],
    }


def apply_development_management_patch() -> None:
    from kbo.league.season import SeasonRunner
    from web.backend.session import GameSession
    import web.backend.draft_management as offseason

    if getattr(GameSession, "_development_management_patch", False):
        return

    # 하루 시작 직전 부상 공백만 자동 콜업하고, 정산 후 2군 등록일을 누적한다.
    if not getattr(SeasonRunner, "_development_day_patch", False):
        original_begin_day = SeasonRunner.begin_day
        original_complete_day = SeasonRunner.complete_day

        def begin_day_with_callups(self, managed_tid=None):
            self.development_moves = []
            for team in self.teams:
                for move in auto_cover_injuries(team):
                    move["tid"] = team.tid
                    self.development_moves.append(move)
            return original_begin_day(self, managed_tid)

        def complete_day_with_development(self):
            results = original_complete_day(self)
            accrue_minor_days(self.teams, 1)
            return results

        SeasonRunner.begin_day = begin_day_with_callups
        SeasonRunner.complete_day = complete_day_with_development
        SeasonRunner._development_day_patch = True

    original_init = GameSession.__init__
    original_new_season = GameSession._new_season
    original_load = GameSession.load
    original_news = GameSession.current_news
    original_begin_offseason = offseason._begin_managed_offseason

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        ensure_farms(
            random.Random(f"kbo-farm-init:{self.user_tid}:{self.year}"),
            self.teams, year=self.year)

    def patched_new_season(self):
        if hasattr(self, "teams") and hasattr(self, "year"):
            ensure_farms(
                random.Random(f"kbo-farm-refill:{getattr(self, 'user_tid', '')}:{self.year}"),
                self.teams, year=self.year)
        return original_new_season(self)

    def patched_news(self):
        news = original_news(self)
        moves = getattr(getattr(self, "season", None), "development_moves", [])
        for move in moves:
            if move.get("tid") == self.user_tid:
                text = f"1군 콜업: {move['name']} ({move['group']})"
                if move.get("demoted"):
                    text += f" / {move['demoted']} 2군 이동"
                news.append(text)
        return news

    def patched_load(name: str = "save"):
        session = original_load(name)
        ensure_farms(
            random.Random(
                f"kbo-farm-migrate:{session.user_tid}:{session.year}"),
            session.teams, year=session.year)
        return session

    def begin_offseason_with_development(session, standings):
        report = development_tick(session.rng, session.teams)
        original_begin_offseason(session, standings)
        session.offseason_reports.insert(0, _development_report(report))

    GameSession.__init__ = patched_init
    GameSession._new_season = patched_new_season
    GameSession.current_news = patched_news
    GameSession.load = staticmethod(patched_load)
    offseason._begin_managed_offseason = begin_offseason_with_development
    GameSession._development_management_patch = True
