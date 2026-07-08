"""트레이드 — 윈나우 ↔ 리빌딩 양방향 니즈 교환 (DESIGN_TRADE.md).

성사 3조건: (a) GM 주관 등가성(tol, 후려치기 결렬) (b) 양쪽 니즈 부합
(c) 방향 상보성(윈나우×리빌딩 쌍만 시도). 패키지 뼈대는 '리빌딩의 즉전
베테랑 ↔ 윈나우의 유망주', 가치 격차는 지명권(1R→2R→3R)으로 균형.
GM 주관 = value_of × exp(N(0, σ)) — 평가 차이가 거래를 성사시키고,
받은 유망주의 진짜 미래는 숨김 재능(g/d)이 가른다 (도박성).
오프시즌 체인: 에이징 → 트레이드(지명권 민팅 포함) → FA → 드래프트 → 재정.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field

from ..engine.probability import TUNE, clamp
from ..models.team import DraftPick, Team
from .contracts import value_of
from .draft import need_bonus
from .economy import league_cap


def mint_picks(teams: list[Team], year: int) -> None:
    """당해 드래프트 1~3R 지명권 민팅 (이전 연도 지명권은 소멸)."""
    tr = TUNE["trade"]
    for t in teams:
        t.draft_picks = [DraftPick(year, r, t.tid)
                         for r in range(1, tr["mint_rounds"] + 1)]


def team_phase(rank: int, n_teams: int) -> str:
    """윈나우 / 리빌딩 / 중립 — 최근 순위 기반."""
    tr = TUNE["trade"]
    contend = 1.0 - (rank - 1) / max(1, n_teams - 1)
    if contend >= tr["contend_win"]:
        return "win"
    if contend <= tr["contend_reb"]:
        return "rebuild"
    return "mid"


def _need_frac(team: Team, pos: str) -> float:
    return need_bonus(team, pos) / TUNE["draft"]["need_max_bonus"]


def sellable_veterans(team: Team) -> list:
    """리빌딩의 잉여: 즉전 베테랑 (나이·OVR 하한)."""
    tr = TUNE["trade"]
    from .aging import overall
    return sorted([p for p in team.roster
                   if p.age >= tr["vet_age"] and overall(p) >= tr["vet_min_ovr"]],
                  key=lambda p: overall(p), reverse=True)


def tradable_prospects(team: Team) -> list:
    """윈나우의 잉여: 유망주 (어리고, 주전 코어가 아님)."""
    tr = TUNE["trade"]
    from .aging import overall
    core = set()
    bats = sorted(team.batters, key=lambda x: x.bat_overall, reverse=True)[:9]
    rot = sorted([p for p in team.pitchers if p.pos == "SP"],
                 key=lambda x: x.pit_overall, reverse=True)[:5]
    core = {p.pid for p in bats} | {p.pid for p in rot}
    from .contracts import asset_war
    return sorted([p for p in team.roster
                   if p.age <= tr["young_age"] and p.pid not in core],
                  key=lambda p: asset_war(p, 1.0), reverse=True)


class GMView:
    """팀별 자산 평가 = 시간 선호(phase별 할인율) × GM 노이즈.

    윈나우는 미래를 강하게 할인해 즉전 베테랑을 상대적으로 높게, 유망주·지명권을
    낮게 본다. 리빌딩은 반대. 이 시간 선호 차이가 '둘 다 이득'인 거래를 만든다.
    GM 노이즈는 (팀, 자산)별 1회 관측 캐시 (평가 차이 = 성사 촉진 + 도박성).
    """

    def __init__(self, rng: random.Random, cap: float, year: int,
                 phases: dict[str, str]):
        self.rng, self.cap, self.year = rng, cap, year
        self.phases = phases
        self.cache: dict = {}

    def value(self, tid: str, asset) -> float:
        key = (tid, id(asset))
        if key not in self.cache:
            tr = TUNE["trade"]
            ph = self.phases.get(tid, "mid")
            disc = (tr["disc_win"] if ph == "win" else
                    tr["disc_reb"] if ph == "rebuild" else None)
            pm = (tr["pick_mult_win"] if ph == "win" else
                  tr["pick_mult_reb"] if ph == "rebuild" else 1.0)
            obj = value_of(asset, self.cap, 1.0, self.year,
                           discount=disc, pick_mult=pm)
            noise = math.exp(self.rng.gauss(0.0, tr["gm_noise"]))
            self.cache[key] = obj * noise
        return self.cache[key]

    def objective(self, asset) -> float:
        """중립 관점 객관 가치 (검증용 — 기준 할인율, 노이즈 없음)."""
        return value_of(asset, self.cap, 1.0, self.year)


@dataclass
class TradeResult:
    year: int
    win_tid: str            # 윈나우 (베테랑 받음)
    reb_tid: str            # 리빌딩 (유망주+지명권 받음)
    veteran: object
    prospects: list         # 윈나우가 내준 유망주(1)
    picks: list             # 윈나우가 얹은 지명권
    obj_win: float          # 객관 가치: 윈나우가 받은 것
    obj_reb: float          # 객관 가치: 리빌딩이 받은 것


@dataclass
class TradeReport:
    attempted: int = 0
    trades: list = field(default_factory=list)   # [TradeResult]


def _try_pair(gm: GMView, win: Team, reb: Team) -> TradeResult | None:
    """윈나우 win ↔ 리빌딩 reb 패키지 탐색. 3조건 전부 충족해야 성사."""
    tr = TUNE["trade"]
    from .aging import overall
    from .draft import _depth
    # (b) 니즈 두 경로: 약점 메꾸기 OR 현 주전 대비 확실한 업그레이드
    vets = [v for v in sellable_veterans(reb)
            if _need_frac(win, v.pos) >= tr["need_min"]
            or overall(v) >= _depth(win, v.pos) + tr["upgrade_gap"]]
    pros = tradable_prospects(win)
    if not vets or not pros:
        return None
    p = pros[0]              # 최고 유망주 (윈나우 잉여)

    for v in vets[:3]:       # 상위 즉전 후보 순서로 패키지 시도
        give: list = [p]     # 윈나우가 내주는 것 (유망주 + 지명권들)
        picks: list = []
        avail_picks = sorted(win.draft_picks, key=lambda pk: pk.round)
        for _ in range(len(avail_picks) + 1):
            # (a) 등가성 — 양쪽 GM 각자의 주관 가치(시간 선호 + 노이즈)로 판정.
            # 각자 "받는 것 ≥ 주는 것 × (1 − tol)" 이어야 (한쪽 큰 손해 = 결렬).
            win_recv = gm.value(win.tid, v)
            win_give = sum(gm.value(win.tid, a) for a in give)
            reb_recv = sum(gm.value(reb.tid, a) for a in give)
            reb_give = gm.value(reb.tid, v)
            ok_win = win_recv >= win_give * (1.0 - tr["tol"])
            ok_reb = reb_recv >= reb_give * (1.0 - tr["tol"])
            if ok_win and ok_reb:
                return TradeResult(gm.year, win.tid, reb.tid, v, [p], picks,
                                   obj_win=gm.objective(v),
                                   obj_reb=sum(gm.objective(a) for a in give))
            if not ok_win:         # 윈나우가 이미 과지불 → 다음 베테랑 후보로
                break
            if not avail_picks:    # 리빌딩 불만 + 얹을 지명권 없음 = 후려치기 거절
                break
            pk = avail_picks.pop(0)    # 격차를 지명권으로 좁힘 (1R→2R→3R)
            picks.append(pk)
            give.append(pk)
    return None


def run_trades(rng: random.Random, teams: list[Team], standings: list[Team],
               year: int) -> TradeReport:
    """오프시즌 트레이드 1회. standings: 전 시즌 순위(우승→꼴찌)."""
    tr = TUNE["trade"]
    mint_picks(teams, year)
    n = len(teams)
    rank = {t.tid: i for i, t in enumerate(standings, 1)}
    phases = {t.tid: team_phase(rank[t.tid], n) for t in teams}
    gm = GMView(rng, league_cap(year), year, phases)
    rep = TradeReport()

    winnows = [t for t in standings if phases[t.tid] == "win"]
    rebuilds = [t for t in standings if phases[t.tid] == "rebuild"]
    done: dict[str, int] = {}
    # (c) 상보성: 윈나우×리빌딩 쌍만, 상위 윈나우 × 하위 리빌딩부터
    for w in winnows:
        for r in reversed(rebuilds):
            if len(rep.trades) >= tr["max_league"]:
                return rep
            if done.get(w.tid, 0) >= tr["max_per_team"] \
                    or done.get(r.tid, 0) >= tr["max_per_team"]:
                continue
            rep.attempted += 1
            deal = _try_pair(gm, w, r)
            if deal is None:
                continue
            # 자산 이동: 베테랑 → 윈나우, 유망주+지명권 → 리빌딩
            v = deal.veteran
            r.roster.remove(v)
            v.team_id = w.tid
            w.roster.append(v)
            for p in deal.prospects:
                w.roster.remove(p)
                p.team_id = r.tid
                r.roster.append(p)
            for pk in deal.picks:
                w.draft_picks.remove(pk)
                r.draft_picks.append(pk)
            done[w.tid] = done.get(w.tid, 0) + 1
            done[r.tid] = done.get(r.tid, 0) + 1
            rep.trades.append(deal)
    return rep
