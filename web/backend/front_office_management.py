"""게임 세션 수명주기에 프런트 평가를 연결한다."""
from __future__ import annotations

from kbo.league.front_office import (create_objective, ensure_front_office,
                                     evaluate_season)


def apply_front_office_patch() -> None:
    from web.backend.session import GameSession

    if getattr(GameSession, "_front_office_patch", False):
        return

    original_init = GameSession.__init__
    original_load = GameSession.load
    original_season_end = GameSession._season_end

    def session_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.owner_confidence = 65.0
        self.front_office_history = []
        self.current_objective = create_objective(self)

    def session_load(name: str = "save"):
        session = original_load(name)
        ensure_front_office(session)
        return session

    def season_end(self):
        previous_count = len(getattr(self, "history", []))
        original_season_end(self)
        ensure_front_office(self)
        if len(self.history) > previous_count:
            evaluate_season(self, self.history[-1])
        self.current_objective = create_objective(self)

    GameSession.__init__ = session_init
    GameSession.load = staticmethod(session_load)
    GameSession._season_end = season_end
    GameSession._front_office_patch = True
