"""런처·첫 실행 화면용 상태 및 릴리스 메타데이터 API."""
from __future__ import annotations

import os
import platform
import sys

from fastapi import APIRouter

from kbo.version import RELEASE_NAME, __version__
from web.backend.session import SAVE_DIR

router = APIRouter()


@router.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@router.get("/api/meta")
def metadata():
    save_path = os.path.join(SAVE_DIR, "save.pkl")
    return {
        "name": "KBO 매니저",
        "version": __version__,
        "release_name": RELEASE_NAME,
        "python": platform.python_version(),
        "platform": platform.system(),
        "save_exists": os.path.isfile(save_path),
        "frozen": bool(getattr(sys, "frozen", False)),
    }
