"""웹 백엔드 초기화.

실시간 경기 교체와 사용자 트레이드·FA·보상선수·드래프트·2군 육성·구단 성향·프런트 평가·구단주 이벤트 확장을 등록한다.
"""
from fastapi import FastAPI

from kbo.engine.substitution_patch import enable_substitutions
from web.backend.draft_management import apply_draft_management_patch
from web.backend.development_management import apply_development_management_patch
from web.backend.engagement_management import apply_engagement_patch
from web.backend.fa_compensation_management import apply_fa_compensation_patch
from web.backend.front_office_management import apply_front_office_patch
from web.backend.team_identity_management import apply_team_identity_patch


def _sub_text(ev: dict) -> str:
    label = {"pinch_hitter": "대타", "pinch_runner": "대주자",
             "defensive": "대수비"}.get(ev.get("kind"), "선수 교체")
    text = (f"{ev['inning']}회{ev['half']} {label}: "
            f"{ev['out']['name']} → {ev['in']['name']}")
    if ev.get("base"):
        text += f" ({ev['base']}루)"
    return text


from web.backend import serializers as _ser
if not getattr(_ser, "_substitution_stream_patch", False):
    _original_watch_stream = _ser.watch_stream

    def _watch_stream_with_substitutions(res):
        payload = _original_watch_stream(res)
        for ev in payload["events"]:
            if ev.get("t") == "substitution":
                ev["text"] = _sub_text(ev)
                ev["source_t"] = "substitution"
                ev["t"] = "pitch_change"
        return payload

    _ser.watch_stream = _watch_stream_with_substitutions
    _ser._substitution_stream_patch = True


def _patch_game_session() -> None:
    apply_draft_management_patch()
    apply_development_management_patch()
    apply_fa_compensation_patch()
    apply_team_identity_patch()
    apply_front_office_patch()
    apply_engagement_patch()

    from web.backend.session import GameSession
    if getattr(GameSession, "_substitution_instance_patch", False):
        return
    original_start_live = GameSession.start_live
    original_require_live = GameSession.require_live

    def start_live_with_substitutions(self):
        return enable_substitutions(original_start_live(self))

    def require_live_with_substitutions(self):
        return enable_substitutions(original_require_live(self))

    GameSession.start_live = start_live_with_substitutions
    GameSession.require_live = require_live_with_substitutions
    GameSession._substitution_instance_patch = True


if not getattr(FastAPI, "_kbo_extension_router_patch", False):
    _original_fastapi_init = FastAPI.__init__

    def _fastapi_init_with_extensions(self, *args, **kwargs):
        _original_fastapi_init(self, *args, **kwargs)
        _patch_game_session()
        from web.backend.substitution_api import router as substitution_router
        from web.backend.trade_api import router as trade_router
        from web.backend.fa_api import router as fa_router
        from web.backend.fa_compensation_api import router as compensation_router
        from web.backend.draft_api import router as draft_router
        from web.backend.development_api import router as development_router
        from web.backend.team_identity_api import router as identity_router
        from web.backend.front_office_api import router as front_office_router
        from web.backend.engagement_api import router as engagement_router
        self.include_router(substitution_router)
        self.include_router(trade_router)
        self.include_router(fa_router)
        self.include_router(compensation_router)
        self.include_router(draft_router)
        self.include_router(development_router)
        self.include_router(identity_router)
        self.include_router(front_office_router)
        self.include_router(engagement_router)

    FastAPI.__init__ = _fastapi_init_with_extensions
    FastAPI._kbo_extension_router_patch = True
