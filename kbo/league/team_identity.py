"""구단별 감독·스카우팅·운영 성향.

성향은 실제 구단 평가가 아니라 게임 안에서 AI 의사결정을 차별화하기 위한
고정 프로필이다. 사용자 직접 선택은 제한하지 않고 AI 추천·상대 판단에만 반영한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..engine.probability import clamp
from ..models.player import Player


@dataclass(frozen=True)
class TeamIdentity:
    key: str
    label: str
    manager_style: str
    strategy: str              # win_now | balanced | rebuild
    offense_focus: str         # balanced | contact | power | speed | defense
    pitching_focus: str        # balanced | velocity | control | stuff | stamina
    scouting: float            # 높을수록 관측 오차 감소
    risk: float                # 0 보수적 ~ 1 고위험·고실링
    trade_aggression: float    # 수락 허용 폭
    fa_aggression: float       # 외부 FA 프리미엄
    development: float         # 젊은 선수·지명권 선호
    description: str


PROFILES: dict[str, TeamIdentity] = {
    "KIA": TeamIdentity("contender-balanced", "우승권 균형 운영", "균형형 감독", "win_now",
                        "balanced", "stuff", 1.02, 0.48, 1.05, 1.08, 0.95,
                        "즉시전력과 전력 균형을 함께 중시한다."),
    "LG": TeamIdentity("pitching-control", "마운드 안정 우선", "투수 운영형 감독", "win_now",
                       "contact", "control", 1.08, 0.38, 0.96, 1.04, 0.92,
                       "제구와 수비 안정성이 높은 즉시전력을 선호한다."),
    "DSN": TeamIdentity("development-pipeline", "육성 파이프라인", "육성형 감독", "balanced",
                        "power", "stamina", 1.05, 0.66, 0.96, 0.92, 1.14,
                        "장기 성장과 선발 자원 축적에 비중을 둔다."),
    "SSG": TeamIdentity("veteran-power", "베테랑·장타 윈나우", "공격형 감독", "win_now",
                        "power", "velocity", 0.96, 0.58, 1.13, 1.15, 0.82,
                        "고위험 장타와 즉시전력 영입에 적극적이다."),
    "SAM": TeamIdentity("youth-rebuild", "젊은 코어 재건", "성장형 감독", "rebuild",
                        "defense", "control", 1.10, 0.72, 0.90, 0.82, 1.22,
                        "젊은 선수와 지명권을 오래 보유하며 코어를 만든다."),
    "KT": TeamIdentity("analytical-balance", "데이터 기반 균형", "분석형 감독", "balanced",
                       "balanced", "balanced", 1.16, 0.42, 0.98, 0.98, 1.02,
                       "평가 오차가 작고 포지션 가치와 효율을 중시한다."),
    "LTE": TeamIdentity("contact-defense", "컨택·수비 야구", "수비형 감독", "balanced",
                        "contact", "control", 1.00, 0.30, 0.92, 0.94, 1.04,
                        "컨택과 수비, 제구가 안정적인 선수를 선호한다."),
    "HWE": TeamIdentity("high-variance-rebuild", "고실링 재건", "도전형 감독", "rebuild",
                        "power", "velocity", 0.90, 0.88, 1.10, 0.90, 1.25,
                        "현재 성적보다 고실링 유망주와 강한 툴에 베팅한다."),
    "NC": TeamIdentity("pitching-development", "투수 육성 중심", "마운드 육성형 감독", "balanced",
                       "speed", "stuff", 1.08, 0.70, 1.00, 0.96, 1.16,
                       "구위 좋은 투수와 운동능력 높은 야수를 길게 육성한다."),
    "KWM": TeamIdentity("speed-youth", "기동력·젊은 야수", "기동력형 감독", "rebuild",
                        "speed", "stamina", 0.98, 0.78, 1.02, 0.86, 1.20,
                        "젊은 야수의 주루·수비 범위와 미래가치를 높게 본다."),
}

DEFAULT_IDENTITY = TeamIdentity(
    "balanced-default", "균형 운영", "균형형 감독", "balanced",
    "balanced", "balanced", 1.0, 0.5, 1.0, 1.0, 1.0,
    "현재 전력과 미래가치를 균형 있게 평가한다.",
)


def ensure_team_identities(teams) -> None:
    for team in teams:
        identity = getattr(team, "identity", None)
        if not isinstance(identity, TeamIdentity):
            team.identity = PROFILES.get(team.tid, DEFAULT_IDENTITY)


def identity_of(team) -> TeamIdentity:
    identity = getattr(team, "identity", None)
    if isinstance(identity, TeamIdentity):
        return identity
    return PROFILES.get(team.tid, DEFAULT_IDENTITY)


def identity_payload(team) -> dict:
    identity = identity_of(team)
    payload = asdict(identity)
    payload["strategy_label"] = {
        "win_now": "윈나우", "balanced": "균형", "rebuild": "리빌딩",
    }[identity.strategy]
    payload["offense_label"] = {
        "balanced": "균형", "contact": "컨택", "power": "장타",
        "speed": "기동력", "defense": "수비",
    }[identity.offense_focus]
    payload["pitching_label"] = {
        "balanced": "균형", "velocity": "구속", "control": "제구",
        "stuff": "구위", "stamina": "선발 내구성",
    }[identity.pitching_focus]
    return payload


def effective_phase(team, rank: int, n_teams: int) -> str:
    """순위와 구단 장기 기조를 합쳐 이번 오프시즌 운영 단계를 결정한다."""
    identity = identity_of(team)
    contend = 1.0 - (rank - 1) / max(1, n_teams - 1)
    bias = {"win_now": 0.18, "balanced": 0.0, "rebuild": -0.18}[identity.strategy]
    score = contend + bias
    if score >= 0.68:
        return "win"
    if score <= 0.32:
        return "rebuild"
    return "mid"


def scouting_sigma(team, base_sigma: float) -> float:
    identity = identity_of(team)
    return base_sigma / clamp(identity.scouting, 0.75, 1.30)


def _tool_score(player: Player, focus: str) -> float:
    if player.is_pitcher:
        r = player.pit
        groups = {
            "velocity": r.velocity,
            "control": r.control,
            "stuff": (r.stuff + r.breaking) / 2,
            "stamina": r.stamina,
            "balanced": (r.velocity + r.control + r.stuff + r.stamina + r.breaking) / 5,
        }
    else:
        r = player.bat
        groups = {
            "contact": (r.contact + r.eye) / 2,
            "power": r.power,
            "speed": (r.speed + r.fielding) / 2,
            "defense": (r.fielding + r.arm) / 2,
            "balanced": (r.contact + r.power + r.eye + r.speed + r.fielding + r.arm) / 6,
        }
    return groups.get(focus, groups["balanced"])


def player_fit(team, player: Player) -> float:
    """구단 스타일 적합도. 대략 -0.12~+0.18 배율 범위."""
    identity = identity_of(team)
    focus = identity.pitching_focus if player.is_pitcher else identity.offense_focus
    tool = _tool_score(player, focus)
    centered = clamp((tool - 55.0) / 35.0, -1.0, 1.0)
    age_signal = clamp((27.0 - player.age) / 9.0, -1.0, 1.0)
    future_weight = (identity.development - 1.0) * age_signal
    risk_weight = (identity.risk - 0.5) * abs(centered) * 0.12
    return clamp(centered * 0.12 + future_weight * 0.35 + risk_weight, -0.12, 0.18)


def draft_fit_bonus(team, player: Player, rnd: int) -> float:
    identity = identity_of(team)
    style = player_fit(team, player) * 4.0
    youth = clamp((23 - player.age) / 5.0, 0.0, 1.0)
    upside = youth * (identity.risk - 0.5) * (0.35 if rnd <= 3 else 0.75)
    return style + upside


def fa_offer_multiplier(team, player: Player) -> float:
    identity = identity_of(team)
    return clamp(identity.fa_aggression * (1.0 + player_fit(team, player)), 0.78, 1.28)


def trade_asset_multiplier(team, asset, phase: str) -> float:
    identity = identity_of(team)
    if isinstance(asset, Player):
        mult = 1.0 + player_fit(team, asset)
        if asset.age <= 25:
            mult *= identity.development
        elif asset.age >= 31 and phase == "win":
            mult *= 1.0 + max(0.0, identity.trade_aggression - 1.0) * 0.5
        return clamp(mult, 0.72, 1.35)
    # 지명권은 리빌딩·육성 구단이 더 높게 평가한다.
    return clamp(identity.development * (1.08 if phase == "rebuild" else 0.94 if phase == "win" else 1.0),
                 0.72, 1.35)


def trade_tolerance(team) -> float:
    return clamp(identity_of(team).trade_aggression, 0.80, 1.22)
