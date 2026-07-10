"""웹 백엔드 초기화.

사용자가 직접 운영하는 경기 인스턴스에만 Part 2B 교체 기능을 활성화하고,
FastAPI 앱이 생성될 때 전용 라우터를 등록한다.
"""
from fastapi import FastAPI

from kbo.engine.substitution_patch import enable_substitutions


def _sub_text(ev: dict) -> str:
    label = {"pinch_hitter": "대타", "pinch_runner": "대주자",
             "defensive": "대수비"}.get(ev.get("kind"), "선수 교체")
    text = (f"{ev['inning']}회{ev['half']} {label}: "
            f"{ev['out']['name']} → {ev['in']['name']}")
    if ev.get("base"):
        text += f" ({ev['base']}루)"
    return text


# 완료 경기 관전 스트림에서도 교체 로그가 보이도록 표현 계층만 확장한다.
from web.backend import serializers as _ser
if not getattr(_ser, "_substitution_stream_patch", False):
    _original_watch_stream = _ser.watch_stream

    def _watch_stream_with_substitutions(res):
        payload = _original_watch_stream(res)
        for ev in payload["events"]:
            if ev.get("t") == "substitution":
                ev["text"] = _sub_text(ev)
                ev["source_t"] = "substitution"
                ev["t"] = "pitch_change"  # 기존 Watch.jsx의 교체 스텝 재사용
        return payload

    _ser.watch_stream = _watch_stream_with_substitutions
    _ser._substitution_stream_patch = True


def _patch_game_session() -> None:
    """신규·불러온 실시간 경기 모두 인스턴스 단위로 교체 기능을 보장한다."""
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


# main.py를 크게 수정하지 않고 앱 생성 시 세션 패치와 교체 API를 등록한다.
if not getattr(FastAPI, "_kbo_substitution_router_patch", False):
    _original_fastapi_init = FastAPI.__init__

    def _fastapi_init_with_substitutions(self, *args, **kwargs):
        _original_fastapi_init(self, *args, **kwargs)
        _patch_game_session()
        from web.backend.substitution_api import router
        self.include_router(router)

    FastAPI.__init__ = _fastapi_init_with_substitutions
    FastAPI._kbo_substitution_router_patch = True
