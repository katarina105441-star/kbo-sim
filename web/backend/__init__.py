"""웹 백엔드 초기화.

웹 실시간 경기에서 경기 중 야수 교체 확장을 활성화하고, FastAPI 앱이 생성될 때
Part 2B 라우터를 자동 등록한다. 콘솔의 기본 자동 경기 경로는 변경하지 않는다.
"""
from fastapi import FastAPI

from kbo.engine.substitution_patch import apply_substitution_patch

apply_substitution_patch()


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
        return payload

    _ser.watch_stream = _watch_stream_with_substitutions
    _ser._substitution_stream_patch = True


# main.py를 크게 수정하지 않고 앱 생성 시 교체 API 라우터를 등록한다.
if not getattr(FastAPI, "_kbo_substitution_router_patch", False):
    _original_fastapi_init = FastAPI.__init__

    def _fastapi_init_with_substitutions(self, *args, **kwargs):
        _original_fastapi_init(self, *args, **kwargs)
        from web.backend.substitution_api import router
        self.include_router(router)

    FastAPI.__init__ = _fastapi_init_with_substitutions
    FastAPI._kbo_substitution_router_patch = True
