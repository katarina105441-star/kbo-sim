"""컨디션(폼) 시스템 — 시즌 내/시즌 간 개인 변동성 확대 (리그 평균은 0 유지).

2층 구조:
- form_season: 시즌 시작 시 N(0,1) 추첨 (클램프 ±2.2) — "커리어하이/부진 시즌"
- form_day: OU 과정 (감쇠 0.88 → 스트릭 지속 체감 ~8일) — "핫/콜드 스트릭"
로짓 반영 폭은 TUNE["form"] 스케일로 제한 — 컨디션이 실력을 뒤집지 않는다.
"""
from __future__ import annotations

from .probability import TUNE


def draw_season_form(rng, teams) -> None:
    """시즌 시작 시 전 선수의 시즌 폼 추첨."""
    for t in teams:
        for p in t.roster:
            p.form_season = max(-2.2, min(2.2, rng.gauss(0.0, 1.0)))
            p.form_day = 0.0


def daily_form_tick(rng, teams) -> None:
    """경기일마다 일일 폼 갱신 (OU 과정)."""
    f = TUNE["form"]
    decay, vol = f["decay"], f["vol"]
    for t in teams:
        for p in t.roster:
            p.form_day = p.form_day * decay + rng.gauss(0.0, vol)
