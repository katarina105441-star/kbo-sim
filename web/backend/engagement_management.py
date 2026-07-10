"""게임 세션 진행에 구단주 이벤트·보상·업적을 연결한다."""
from __future__ import annotations

from kbo.league.engagement import (apply_season_rewards, ensure_engagement,
                                   maybe_issue_event, next_unissued_milestone)


def apply_engagement_patch() -> None:
    from web.backend.session import GameSession

    if getattr(GameSession, "_engagement_patch", False):
        return

    original_init = GameSession.__init__
    original_load = GameSession.load
    original_advance = GameSession.advance
    original_start_live = GameSession.start_live
    original_season_end = GameSession._season_end

    def session_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        ensure_engagement(self)

    def session_load(name: str = "save"):
        session = original_load(name)
        ensure_engagement(session)
        maybe_issue_event(session)
        return session

    def advance(self, unit: str):
        ensure_engagement(self)
        if self.pending_owner_event is not None:
            raise RuntimeError("구단주 이벤트에 먼저 응답해야 합니다.")

        # '시즌 끝까지'도 이벤트 시점을 건너뛰지 않고 다음 이사회에서 한 번 멈춘다.
        milestone = next_unissued_milestone(self) if unit == "season_end" else None
        if milestone is not None:
            played = 0
            while int(self.season.day) < milestone and not self.season.finished:
                remaining = milestone - int(self.season.day)
                step = "month" if remaining >= 24 else ("series" if remaining >= 3 else "day")
                out = original_advance(self, step)
                played += out["played_days"]
            maybe_issue_event(self)
            return {"played_days": played}

        out = original_advance(self, unit)
        maybe_issue_event(self)
        return out

    def start_live(self):
        ensure_engagement(self)
        if self.pending_owner_event is not None:
            raise RuntimeError("구단주 이벤트에 먼저 응답해야 합니다.")
        return original_start_live(self)

    def season_end(self):
        original_season_end(self)
        apply_season_rewards(self)

    GameSession.__init__ = session_init
    GameSession.load = staticmethod(session_load)
    GameSession.advance = advance
    GameSession.start_live = start_live
    GameSession._season_end = season_end
    GameSession._engagement_patch = True
