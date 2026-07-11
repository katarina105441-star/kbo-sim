"""게임 세션에 해임·재취업·은퇴까지 감독 커리어 수명주기를 연결한다."""
from __future__ import annotations

from kbo.league.career_legacy import ensure_career_legacy, maybe_auto_retire
from kbo.league.front_office import create_objective
from kbo.league.manager_career import ensure_manager_career, process_season_career


def apply_manager_career_patch() -> None:
    from web.backend.session import GameSession

    if getattr(GameSession, "_manager_career_patch", False):
        return

    original_init = GameSession.__init__
    original_load = GameSession.load
    original_advance = GameSession.advance
    original_start_live = GameSession.start_live
    original_season_end = GameSession._season_end
    original_new_season = GameSession._new_season

    def session_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        ensure_manager_career(self)
        ensure_career_legacy(self)

    def session_load(name: str = "save"):
        session = original_load(name)
        ensure_manager_career(session)
        ensure_career_legacy(session)
        return session

    def advance(self, unit: str):
        ensure_career_legacy(self)
        if self.career_status == "dismissed":
            raise RuntimeError("재취업할 구단을 먼저 선택해야 합니다.")
        if self.career_status == "retired":
            raise RuntimeError("은퇴한 감독의 커리어는 더 진행할 수 없습니다.")
        return original_advance(self, unit)

    def start_live(self):
        ensure_career_legacy(self)
        if self.career_status == "dismissed":
            raise RuntimeError("재취업할 구단을 먼저 선택해야 합니다.")
        if self.career_status == "retired":
            raise RuntimeError("은퇴한 감독은 경기를 직접 운영할 수 없습니다.")
        return original_start_live(self)

    def season_end(self):
        original_season_end(self)
        process_season_career(self)
        maybe_auto_retire(self)

    def new_season(self):
        original_new_season(self)
        if hasattr(self, "owner_confidence"):
            self.current_objective = create_objective(self)
        if hasattr(self, "career_status") and self.career_status == "employed":
            self.season.record_watch = {self.user_tid}

    GameSession.__init__ = session_init
    GameSession.load = staticmethod(session_load)
    GameSession.advance = advance
    GameSession.start_live = start_live
    GameSession._season_end = season_end
    GameSession._new_season = new_season
    GameSession._manager_career_patch = True
