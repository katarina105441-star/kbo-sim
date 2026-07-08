"""FA 자유계약 — 경매식 시장 (DESIGN_FA.md).

봉인식 단발 입찰 + 프리미엄: 구단 AI가 약점·경쟁력 기반 프리미엄을 얹어 오퍼,
선수가 appeal = w_money·money + w_play·play + w_win·win 로 선택 (가중치는
나이/성향 편향 → 노장 우승지향·젊은FA 출전지향의 FM식 서사 창발).
등급별 보상금(A300/B200/C150%)이 이동 브레이크. 대다수는 잔류(원팀 loyalty).
오프시즌 체인: 에이징(은퇴) → FA → 드래프트(구멍 refill) → 재정.
시즌 간 로직 — 경기 엔진은 호출하지 않는다 (회귀 가드).
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field

from ..engine.probability import TUNE, clamp
from ..models.player import Player
from ..models.team import Team
from .aging import overall
from .contracts import asset_war, dollar_per_war
from .draft import need_bonus
from .economy import league_cap, team_payroll


def seed_service_years(teams: list[Team]) -> None:
    """초기 로스터 서비스타임 근사 부트스트랩 (1회): 나이 − 20.

    신규 시뮬 시작 시 전원 0이면 8시즌간 FA가 전무해지므로, 커리어 중반
    베테랑(최형우 41 → 21년)이 이미 자격을 갖게 나이 기반으로 시딩한다.
    재자격 시점을 나이로 스태거해 1년차 일시 자격 홍수를 4년에 분산한다.
    """
    stagger = int(TUNE["fa"]["reelig"])
    for t in teams:
        for p in t.roster:
            if p.service_years == 0.0:
                p.service_years = max(0.0, p.age - 20.0)
                p.fa_eligible_at = p.service_years + (p.age % stagger)


def eligible(p: Player) -> bool:
    f = TUNE["fa"]
    return p.service_years >= max(f["service_req"], p.fa_eligible_at)


def assign_grades(declared: list[Player]) -> None:
    """현재 연봉(최근 연봉 프록시) 상위 1/3 = A, 중간 1/3 = B, 나머지 C."""
    ranked = sorted(declared, key=lambda p: p.contract.salary, reverse=True)
    n = len(ranked)
    for i, p in enumerate(ranked):
        p.fa_grade = "A" if i < n / 3 else ("B" if i < 2 * n / 3 else "C")


def need_frac(team: Team, pos: str) -> float:
    """포지션 뎁스 부족도 0~1 (드래프트 Need 재사용, 보너스 → 원비율 환산)."""
    return need_bonus(team, pos) / TUNE["draft"]["need_max_bonus"]


def player_weights(rng: random.Random, p: Player) -> tuple[float, float, float]:
    """(w_money, w_play, w_win) — 나이 편향 + 약한 노이즈, 합 1 정규화."""
    f = TUNE["fa"]
    wm, wp, ww = f["w_base"]
    if p.age >= f["vet_age"]:        # 노장: 우승 노림 (+win −play)
        ww += f["tilt"]; wp -= f["tilt"]
    elif p.age <= f["young_age"]:    # 젊은 FA: 출전기회 (+play −money)
        wp += f["tilt"]; wm -= f["tilt"]
    ws = [max(0.02, w + rng.gauss(0, f["w_noise"])) for w in (wm, wp, ww)]
    s = sum(ws)
    return ws[0] / s, ws[1] / s, ws[2] / s


def fair_aav(p: Player, cap: float, year: int) -> float:
    """FA 적정 AAV — 주전 가정(role 1.0) 자산가치 기반 연 환산."""
    c = TUNE["contract"]
    horizon_v = asset_war(p, 1.0) * dollar_per_war(cap, year)
    yrs = contract_years(p)
    return max(c["min_salary"], horizon_v / max(1, TUNE["contract"]["horizon"]) *
               (1.0 if yrs <= 2 else 1.1))   # 장기계약 대어는 소폭 프리미엄


def contract_years(p: Player) -> int:
    for age_hi, yrs in TUNE["fa"]["contract_years"]:
        if p.age <= age_hi:
            return yrs
    return 1


def compensation(p: Player) -> float:
    """보상금(억) = 전년연봉 × 등급 배수 (영입팀 → 원소속팀)."""
    return p.contract.salary * TUNE["fa"]["comp"].get(p.fa_grade, 1.5)


@dataclass
class FASigning:
    player: Player
    from_tid: str
    to_tid: str          # from == to 이면 잔류
    grade: str
    aav: float
    fair: float
    comp: float
    n_offers: int
    w: tuple             # 선수 성향 (money, play, win)


@dataclass
class FAReport:
    declared: int = 0
    signings: list = field(default_factory=list)   # [FASigning]
    released: list = field(default_factory=list)   # 로스터 25 초과 방출

    @property
    def moved(self):
        return [s for s in self.signings if s.to_tid != s.from_tid]


def _win_score(rank: int, n: int) -> float:
    return 1.0 - (rank - 1) / max(1, n - 1)


def run_fa_market(rng: random.Random, teams: list[Team], standings: list[Team],
                  year: int) -> FAReport:
    """봉인식 단발 경매. standings: 전 시즌 순위(우승→꼴찌)."""
    f = TUNE["fa"]
    cap = league_cap(year)
    rank = {t.tid: i for i, t in enumerate(standings, 1)}
    n_teams = len(teams)
    by_tid = {t.tid: t for t in teams}

    declared = [p for t in teams for p in t.roster if eligible(p)]
    rep = FAReport(declared=len(declared))
    if not declared:
        return rep
    assign_grades(declared)
    limit = max(1, len(declared) // f["max_signings_divisor"])
    signed_count = {t.tid: 0 for t in teams}
    spent = {t.tid: 0.0 for t in teams}   # 시장당 누적 FA 지출 (AAV+보상금)

    # 대어부터 처리 (인원 한도가 상위 FA에 먼저 소진되는 현실 순서)
    for p in sorted(declared, key=lambda x: asset_war(x, 1.0), reverse=True):
        home = by_tid[p.team_id]
        fv = fair_aav(p, cap, year)
        comp = compensation(p)
        yrs = contract_years(p)
        w = player_weights(rng, p)

        offers = []   # (team, aav, is_home)
        if comp <= fv * yrs * f["comp_tolerance"]:   # 보상금 > 계약가치면 아무도 안 붙음
            for t in teams:
                if t.tid == p.team_id:
                    continue
                if signed_count[t.tid] >= limit:
                    continue
                nf = need_frac(t, p.pos)
                if nf < f["need_min"]:
                    continue
                premium = min(f["overpay_cap"],
                              f["overpay_need"] * nf
                              + f["overpay_win"] * _win_score(rank[t.tid], n_teams))
                aav = fv * (1.0 + premium)
                # 총비용(입찰+보상금) — 시장당 누적 지출이 예산 일정 비율 이내
                if spent[t.tid] + aav + comp > t.budget * f["spend_frac"]:
                    continue
                offers.append((t, aav, False))
        offers.append((home, fv, True))     # 원소속 잔류 오퍼 (프리미엄 없음)

        max_aav = max(o[1] for o in offers)
        best, best_ap = None, -1.0
        for t, aav, is_home in offers:
            money = aav / max_aav
            play = need_frac(t, p.pos) if not is_home else clamp(
                need_frac(t, p.pos) + 0.5, 0.0, 1.0)   # 원팀에선 이미 자리 있음
            win = _win_score(rank[t.tid], n_teams)
            ap = (w[0] * money + w[1] * play + w[2] * win
                  + (f["loyalty"] if is_home else 0.0)
                  + rng.gauss(0, f["choice_noise"]))
            if ap > best_ap:
                best, best_ap = (t, aav, is_home), ap

        t, aav, is_home = best
        p.contract.salary = round(aav, 2)
        p.contract.years = yrs
        p.contract.signing_bonus = round(aav * yrs *
                                         TUNE["contract"]["signing_bonus_frac"], 2)
        p.fa_eligible_at = p.service_years + f["reelig"]
        rep.signings.append(FASigning(p, p.team_id, t.tid, p.fa_grade,
                                      round(aav, 2), round(fv, 2),
                                      round(comp, 2), len(offers) - 1, w))
        if not is_home:                     # 이적: 로스터 이동 + 보상금 이전
            home.roster.remove(p)
            p.team_id = t.tid
            t.roster.append(p)
            t.budget = round(t.budget - comp, 2)
            home.budget = round(home.budget + comp, 2)
            signed_count[t.tid] += 1
            spent[t.tid] += aav + comp

    # 로스터 25 초과 팀: 최저 가치 선수 방출 (다음 드래프트가 부족팀 refill)
    for t in teams:
        while len(t.roster) > 25:
            cut = min(t.roster, key=lambda x: asset_war(x, 0.5))
            t.roster.remove(cut)
            rep.released.append((t.tid, cut))
    return rep
