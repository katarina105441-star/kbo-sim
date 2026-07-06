"""능력치 → 확률 변환 (엔진의 핵심 수식).

# 모델: 로그오즈(log-odds) 공간의 log5 매치업
모든 이벤트율을 로짓 공간에서 다룬다:

    P(이벤트 | 타자, 투수) = sigmoid( logit(리그평균) + 타자시프트 + 투수시프트 + 상황보정 )

- 타자시프트 = 감도상수 × z(관련 능력치 가중합),  z(r) = (r - ANCHOR) / 50
- 이 형태는 Bill James의 log5와 수학적으로 동일하다
  (logit(P) = logit(B) + logit(P') - logit(L)).
- 전원이 ANCHOR 능력치면 정확히 리그 평균이 나온다 → 밸런스가 구조적으로 통제됨.

# 튜닝
모든 밸런싱 상수는 TUNE 한 곳에만 있다. scripts/calibrate.py로 시즌을 돌려
리그 지표를 목표표와 비교하며 이 값들만 조정한다.
"""
from __future__ import annotations
import math

from ..models.player import Player

# ============================================================
# TUNE — 캘리브레이션 대상 상수 (calibrate.py 사이클로 조정)
# ============================================================
TUNE = {
    # 실효 리그 평균 능력치. 로스터가 주전 위주(평균>50)라서 50보다 높게 앵커링.
    "anchor": 58.0,

    # 리그 기준율 (타석당) — KBO 최근 수년 평균대
    "lg": {
        "k": 0.176,        # 삼진율
        "bb": 0.093,       # 볼넷율
        "hbp": 0.013,      # 사구율
        "hr": 0.0225,      # 홈런율
        "gb_hit": 0.258,   # 땅볼 BABIP
        "ld_hit": 0.700,   # 라인드라이브 BABIP
        "fb_hit": 0.190,   # 뜬공(비홈런) BABIP
        "gb_share": 0.44,  # 인플레이 중 땅볼 비율
        "ld_share": 0.20,  # 라인드라이브 비율
        "sb_success": 0.715,    # 도루 성공률
        "dp_rate": 0.33,        # 병살 상황(땅볼아웃+1루주자+2사미만)의 병살 전환율
        "sf_deep": 0.56,        # 뜬공아웃 시 3루주자 득점 시도 성공 기준율
        "adv_2h_single": 0.68,  # 단타 때 2루주자 득점
        "adv_13_single": 0.35,  # 단타 때 1루주자 3루행
        "adv_1h_double": 0.52,  # 2루타 때 1루주자 득점
        "go_advance": 0.32,     # 땅볼아웃 진루타
        "go_score3": 0.34,      # 2사미만 땅볼아웃 시 3루주자 득점
        "fb_tag23": 0.22,       # 뜬공아웃 시 2루주자 태그업 3루행
        "err": 0.042,           # 아웃 판정 인플레이가 실책으로 바뀔 확률 (팀당 ~95개/시즌)
    },

    # 감도 (로짓 시프트 = 감도 × z). 부호: 양수 = 능력치 높을수록 해당 이벤트 증가
    "sens": {
        "bat_k": -0.85,      # 컨택·선구 → 삼진 감소
        "bat_bb": 0.90,      # 선구 → 볼넷 증가
        "bat_hr": 1.42,      # 파워 → 홈런 증가 (부상 도입 후 홈런왕 꼬리 복원)
        "bat_babip": 0.50,   # 컨택 → 인플레이 안타 증가 (타율왕 꼬리 복원)
        "bat_ifh": 0.30,     # 주루 → 내야안타(땅볼 안타) 증가
        "pit_k": 1.05,       # 구위·구속·변화구 → 탈삼진 증가 (꼬리검증: 에이스 K% 30%대 도달)
        "pit_bb": -1.05,     # 제구 → 볼넷 감소
        "pit_hr": -0.80,     # 구위·변화구 → 피홈런 감소 (꼬리검증: 에이스 분산 확대)
        "pit_babip": -0.55,  # 구위·구속 → 피BABIP 감소 (꼬리검증: 특급 억제 강화)
        "pit_hbp": -0.55,    # 제구 → 사구 감소
        "def_if": -0.22,     # 내야 수비 → 땅볼 안타 감소
        "def_of": -0.20,     # 외야 수비 → 뜬공/라이너 안타 감소
        "err_def": -0.80,    # 수비 → 실책 감소 (BABIP과 같은 수비 능력치 공유)
        "run_speed": 0.50,   # 주루 → 진루/도루 성공 증가
        "of_arm": -0.40,     # 외야 송구 → 추가 진루 감소
        "c_arm": -0.55,      # 포수 송구 → 도루 성공 감소
        "dp_speed": -0.45,   # 타자 주루 → 병살 감소
        "dp_def": 0.30,      # 내야 수비 → 병살 증가
        "gb_tilt": 0.24,     # 투수 변화구·구위 → 땅볼 비율 증가 (share 직접 가감)
        "fb_pow": 0.05,      # 타자 파워 → 뜬공 비율 소폭 증가
    },

    # 플래툰 (승인 사항: 단순화 — 같은 손 매치업이면 타자에게 일괄 소폭 페널티)
    "platoon": {"k": 0.10, "bb": -0.08, "hr": -0.12, "babip": -0.06},

    # 도루 시도율: attempt = base + coef * max(0, z(spd))^1.5, 상한 cap
    # (꼬리검증: 도루왕 평균 55→40대로 완화. cap 0.34→0.28, coef 0.45→0.38)
    "steal": {"base": 0.015, "coef": 0.38, "cap": 0.28},

    # 투수 피로: 한계투구수 = sp_base + sp_per_sta × 스태미나 (불펜은 rp_*)
    # 초과분 비율(over/60)에 fatigue_scale을 곱해 로짓 페널티로 사용
    "fatigue": {
        "sp_base": 45.0, "sp_per_sta": 0.75,
        "rp_base": 16.0, "rp_per_sta": 0.30,
        "scale": 0.9,
        # 총 페널티 상한. 연투 강행 폴백 도입으로 불펜 고갈 병리가 해소되어
        # 1.1 → 1.6으로 완화 (물리적 타당성 한계로만 기능)
        "cap": 1.6,
        # 타순 한 바퀴(TTO) 페널티: 3바퀴째부터 타자에게 로짓 보너스
        "tto3": {"k": -0.06, "hr": 0.09, "babip": 0.05},
        # 선발 등판 간격 (휴식일 수 → 한계투구수 배율 / 등판 시 기본 페널티)
        # 중4일이 기준선(1.0). 중3일 이하 강행은 한계↓ + 구위 저하
        "rest": {
            3: {"mult": 0.85, "pen": 0.10},
            4: {"mult": 1.00, "pen": 0.00},
            5: {"mult": 1.06, "pen": 0.00},
            6: {"mult": 1.10, "pen": 0.00},
        },
        # 불펜 연투: 어제 등판 시 기본 저하 + 투구수 비례, 2연투째 가중.
        # 어제 hard_pitch 이상 던졌거나 2연투면 당일 등판 불가 (비상시 강행)
        "relief": {"day1_base": 0.05, "day1_per_pitch": 0.004,
                   "streak2": 0.15, "hard_pitch": 35},
    },

    # 안타 종류 분화 (타구 유형별 [1루타, 2루타, 3루타] 기본 비율)
    "hit_split": {
        "GB": [0.96, 0.04, 0.00],
        "LD": [0.73, 0.24, 0.03],
        "FB": [0.59, 0.34, 0.07],
        "triple_spd_sens": 0.9,   # 3루타 비율의 주루 민감도
    },

    # 결과별 평균 투구수
    "pitches": {"K": 4.9, "BB": 5.7, "HBP": 3.6, "HR": 3.4, "BIP": 3.4},

    # 포스트시즌: 장기 휴식 팀의 경기감각 저하 (KS 직행팀 초반 고전 재현)
    # idle_days 이상 실전 공백 → 시리즈 시작 시 전 선수 form_day에 음의 쇼크
    # (OU 감쇠로 시리즈가 진행되며 자연 회복)
    "ps_rust": {"idle_days": 6, "shock": 1.5},

    # 컨디션(폼): 능력치를 뒤집지 않는 소폭 로짓 보정 — 분산 확대 전용.
    # 로짓시프트 = season × form_season + day × form_day
    # (form_season ~ N(0,1) 클램프 ±2.2 / form_day는 OU 과정, 정상 sd≈1)
    "form": {
        "season": 0.06,   # 시즌 폼 스케일 (±2σ ≈ 능력치 ±6점 체감)
        "day": 0.05,      # 일일 핫/콜드 스케일
        "decay": 0.88,    # OU 감쇠 (스트릭 지속 ~8일 체감)
        "vol": 0.47,      # OU 변동성 (정상상태 sd 1.0)
    },

    # 부상: 일일 발생 확률 (목표 — 주전 야수 시즌 8~10% 결장)
    "injury": {
        "bat_daily": 0.0072,     # 야수 기본 (경기일당) — 주전 결장 8~10% 목표
        "pit_daily": 0.0035,     # 투수 기본 (비등판일 포함)
        "outing_coef": 0.00009,  # 당일 투구수 1구당 가산 (100구 등판일 +0.009)
        "catcher_mult": 1.5,     # 포수 가중
        "age_coef": 0.035,       # 30세 초과 1세당 +3.5%
        # 결장 기간 분포: (비율, 최소일, 최대일) — 경미/중간/중상/시즌아웃급
        "dur": [(0.60, 2, 7), (0.25, 8, 20), (0.12, 21, 50), (0.03, 60, 120)],
    },
}


# ---------- 기본 수학 ----------
def logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    if x < -30:
        return 1e-13
    if x > 30:
        return 1.0 - 1e-13
    return 1.0 / (1.0 + math.exp(-x))


def z(rating: float) -> float:
    return (rating - TUNE["anchor"]) / 50.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------- 선수별 로짓 시프트 캐싱 (시즌 시작/로드 시 1회) ----------
def precompute_batter(p: Player) -> None:
    b = p.bat
    s = TUNE["sens"]
    p.shifts = {
        "k": s["bat_k"] * z(0.70 * b.contact + 0.30 * b.eye),
        "bb": s["bat_bb"] * z(b.eye),
        "hr": s["bat_hr"] * z(0.80 * b.power + 0.20 * b.contact),
        "babip": s["bat_babip"] * z(b.contact),
        "ifh": s["bat_ifh"] * z(b.speed),
        "run": s["run_speed"] * z(b.speed),
        "dp": s["dp_speed"] * z(b.speed),
        "fb": s["fb_pow"] * z(b.power),
        "z_spd": z(b.speed),
    }


def precompute_pitcher(p: Player) -> None:
    t = p.pit
    s = TUNE["sens"]
    p.shifts = {
        "k": s["pit_k"] * z(0.40 * t.stuff + 0.35 * t.velocity + 0.25 * t.breaking),
        "bb": s["pit_bb"] * z(t.control),
        "hr": s["pit_hr"] * z(0.50 * t.stuff + 0.30 * t.breaking + 0.20 * t.control),
        "babip": s["pit_babip"] * z(0.60 * t.stuff + 0.40 * t.velocity),
        "hbp": s["pit_hbp"] * z(t.control),
        "gb": s["gb_tilt"] * z(0.60 * t.breaking + 0.40 * t.stuff),
    }


def precompute_all(players) -> None:
    for p in players:
        if p.is_pitcher:
            precompute_pitcher(p)
        else:
            precompute_batter(p)


# ---------- 매치업 확률 ----------
def matchup(base: float, bat_shift: float, pit_shift: float, extra: float = 0.0) -> float:
    """log5: logit(리그) + 타자 + 투수 + 상황보정."""
    return sigmoid(logit(base) + bat_shift + pit_shift + extra)


def form_shift(p: Player) -> float:
    """현재 폼의 로짓 시프트 (컨디션 시스템). 리그 평균 0 유지."""
    f = TUNE["form"]
    return f["season"] * p.form_season + f["day"] * p.form_day


def pa_event_probs(batter: Player, pitcher: Player, *, fatigue: float, tto: int,
                   same_hand: bool, park_hr: float = 1.0) -> dict:
    """타석 1차 분기 확률: HBP / K / BB / HR / BIP(인플레이).

    fatigue: 투수 피로 로짓 페널티(0 이상). tto: 타순 몇 바퀴째(1~).
    same_hand: 같은 손 매치업 여부 (플래툰 단순 페널티).
    """
    lg = TUNE["lg"]
    bs, ps = batter.shifts, pitcher.shifts
    pl = TUNE["platoon"] if same_hand else None
    tto3 = TUNE["fatigue"]["tto3"] if tto >= 3 else None

    k_x = bs["k"] + ps["k"] - fatigue * 0.6
    bb_x = bs["bb"] + ps["bb"] + fatigue * 0.8
    hr_x = bs["hr"] + ps["hr"] + fatigue * 0.5
    if pl:
        k_x += pl["k"]; bb_x += pl["bb"]; hr_x += pl["hr"]
    if tto3:
        k_x += tto3["k"]; hr_x += tto3["hr"]
    net_form = form_shift(batter) - form_shift(pitcher)  # 폼 상대값 (핫/콜드)
    if net_form:
        k_x -= net_form * 0.6; bb_x += net_form * 0.5; hr_x += net_form * 0.7

    p_hbp = matchup(lg["hbp"], 0.0, ps["hbp"] + fatigue * 0.3)
    p_k = matchup(lg["k"], k_x, 0.0)
    p_bb = matchup(lg["bb"], bb_x, 0.0)
    p_hr = matchup(lg["hr"], hr_x, 0.0) * park_hr

    total = p_hbp + p_k + p_bb + p_hr
    if total > 0.95:  # 안전장치 (극단 매치업)
        f = 0.95 / total
        p_hbp *= f; p_k *= f; p_bb *= f; p_hr *= f
    return {"HBP": p_hbp, "K": p_k, "BB": p_bb, "HR": p_hr,
            "BIP": 1.0 - (p_hbp + p_k + p_bb + p_hr)}


def ball_type(rng, batter: Player, pitcher: Player) -> str:
    """인플레이 타구 유형: GB(땅볼) / LD(라이너) / FB(뜬공)."""
    lg = TUNE["lg"]
    gb = clamp(lg["gb_share"] + pitcher.shifts["gb"] - batter.shifts["fb"], 0.25, 0.62)
    ld = lg["ld_share"]
    r = rng.random()
    if r < gb:
        return "GB"
    if r < gb + ld:
        return "LD"
    return "FB"


def bip_hit_prob(bt: str, batter: Player, pitcher: Player, *,
                 if_def_z: float, of_def_z: float, fatigue: float,
                 tto: int, same_hand: bool) -> float:
    """타구 유형별 안타 확률 (BABIP). 수비력이 여기에 개입한다."""
    lg = TUNE["lg"]
    s = TUNE["sens"]
    bs, ps = batter.shifts, pitcher.shifts
    x = bs["babip"] + ps["babip"] + fatigue * 0.4
    x += (form_shift(batter) - form_shift(pitcher)) * 0.5  # 폼 → BABIP
    if same_hand:
        x += TUNE["platoon"]["babip"]
    if tto >= 3:
        x += TUNE["fatigue"]["tto3"]["babip"]
    if bt == "GB":
        x += bs["ifh"] + s["def_if"] * if_def_z
        return matchup(lg["gb_hit"], x, 0.0)
    if bt == "LD":
        x += 0.5 * s["def_of"] * of_def_z
        return matchup(lg["ld_hit"], x, 0.0)
    x += s["def_of"] * of_def_z
    return matchup(lg["fb_hit"], x, 0.0)


def hit_kind(rng, bt: str, batter: Player, park_xbh: float = 1.0) -> str:
    """안타 종류: 1B/2B/3B (홈런은 타석 1차 분기에서 이미 처리)."""
    hs = TUNE["hit_split"]
    p1, p2, p3 = hs[bt]
    p3 = p3 * max(0.1, 1.0 + hs["triple_spd_sens"] * batter.shifts["z_spd"])
    p2 = p2 * park_xbh
    tot = p1 + p2 + p3
    r = rng.random() * tot
    if r < p1:
        return "1B"
    if r < p1 + p2:
        return "2B"
    return "3B"


def pitches_for(rng, outcome: str) -> int:
    base = TUNE["pitches"].get(outcome, TUNE["pitches"]["BIP"])
    return max(1, int(round(base + rng.uniform(-1.2, 1.2))))
