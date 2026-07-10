"""중단·재개 가능한 사용자 참여 FA 시장.

기존 ``run_fa_market``의 자격·등급·보상금·AI 오퍼·선수 appeal 계산을 그대로
사용한다. 선수별 봉인식 입찰 직전에 멈춰 사용자가 직접 AAV를 제안하거나 패스,
기존 AI 판단을 선택할 수 있다. 객체는 pickle 저장·복원이 가능하다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.probability import TUNE, clamp
from ..models.player import Player
from ..models.team import Team
from .aging import overall
from .contracts import asset_war
from .economy import league_cap
from .fa import (FAReport, FASigning, _win_score, assign_grades, compensation,
                 contract_years, eligible, fair_aav, need_frac, player_weights)


@dataclass
class PendingFA:
    player: Player
    home_tid: str
    fair: float
    comp: float
    years: int
    weights: tuple[float, float, float]
    ai_offers: list[tuple[str, float, bool]]


class InteractiveFAMarket:
    def __init__(self, rng, teams: list[Team], standings: list[Team],
                 year: int, user_tid: str):
        self.rng = rng
        self.teams = teams
        self.standings = standings
        self.year = year
        self.user_tid = user_tid.upper()
        self.cap = league_cap(year)
        self.rank = {team.tid: i for i, team in enumerate(standings, 1)}
        self.by_tid = {team.tid: team for team in teams}
        self.declared = [p for team in teams for p in team.roster if eligible(p)]
        assign_grades(self.declared)
        self.queue = sorted(self.declared, key=lambda p: asset_war(p, 1.0), reverse=True)
        self.limit = max(1, len(self.declared) // TUNE["fa"]["max_signings_divisor"])
        self.signed_count = {team.tid: 0 for team in teams}
        self.spent = {team.tid: 0.0 for team in teams}
        self.report = FAReport(declared=len(self.declared))
        self.index = 0
        self.pending: PendingFA | None = None
        self.complete = False
        self.last_result: dict | None = None
        self._prepare()

    def _build_ai_offers(self, p: Player, fair: float, comp: float,
                         years: int) -> list[tuple[str, float, bool]]:
        f = TUNE["fa"]
        offers: list[tuple[str, float, bool]] = []
        if comp <= fair * years * f["comp_tolerance"]:
            for team in self.teams:
                if team.tid == p.team_id:
                    continue
                if self.signed_count[team.tid] >= self.limit:
                    continue
                nf = need_frac(team, p.pos)
                if nf < f["need_min"]:
                    continue
                premium = min(
                    f["overpay_cap"],
                    f["overpay_need"] * nf
                    + f["overpay_win"] * _win_score(
                        self.rank[team.tid], len(self.teams)),
                )
                aav = fair * (1.0 + premium)
                if (self.spent[team.tid] + aav + comp
                        > team.budget * f["spend_frac"]):
                    continue
                offers.append((team.tid, aav, False))
        offers.append((p.team_id, fair, True))
        return offers

    def _prepare(self) -> None:
        if self.complete or self.pending is not None:
            return
        if self.index >= len(self.queue):
            self._finish()
            return
        p = self.queue[self.index]
        fair = fair_aav(p, self.cap, self.year)
        comp = compensation(p)
        years = contract_years(p)
        weights = player_weights(self.rng, p)
        self.pending = PendingFA(
            p, p.team_id, fair, comp, years, weights,
            self._build_ai_offers(p, fair, comp, years),
        )

    def _finish(self) -> None:
        if self.complete:
            return
        for team in self.teams:
            while len(team.roster) > 25:
                cut = min(team.roster, key=lambda p: asset_war(p, 0.5))
                team.roster.remove(cut)
                self.report.released.append((team.tid, cut))
        self.complete = True
        self.pending = None

    def _user_offer_limit(self, pending: PendingFA) -> float:
        team = self.by_tid[self.user_tid]
        if self.signed_count[self.user_tid] >= self.limit:
            return 0.0
        comp_cost = 0.0 if self.user_tid == pending.home_tid else pending.comp
        remaining = team.budget * TUNE["fa"]["spend_frac"] - self.spent[self.user_tid]
        return max(0.0, remaining - comp_cost)

    def _validate_offer(self, aav: float) -> float:
        if self.pending is None:
            raise RuntimeError("처리할 FA 선수가 없습니다.")
        aav = round(float(aav), 2)
        minimum = TUNE["contract"]["min_salary"]
        if aav < minimum:
            raise ValueError(f"제안 연봉은 최소 {minimum:.2f}억 이상이어야 합니다.")
        maximum = self._user_offer_limit(self.pending)
        if maximum <= 0:
            raise ValueError("FA 영입 한도 또는 예산 한도를 초과했습니다.")
        if aav > maximum + 1e-9:
            raise ValueError(f"현재 제안 가능한 최대 AAV는 {maximum:.2f}억입니다.")
        return aav

    def _resolve(self, mode: str, user_aav: float | None = None) -> dict:
        pending = self.pending
        if pending is None:
            raise RuntimeError("처리할 FA 선수가 없습니다.")
        p = pending.player
        offers = list(pending.ai_offers)

        # auto는 기존 run_fa_market의 오퍼 목록을 그대로 사용한다.
        # pass는 사용자 구단 오퍼를 제거한다. offer는 기존 사용자 오퍼를 교체한다.
        if mode in ("pass", "offer"):
            offers = [offer for offer in offers if offer[0] != self.user_tid]
        if mode == "offer":
            aav = self._validate_offer(user_aav)
            offers.append((self.user_tid, aav, self.user_tid == pending.home_tid))
        elif mode not in ("auto", "pass"):
            raise ValueError(f"알 수 없는 FA 처리 방식입니다: {mode}")

        # 원소속팀 사용자가 패스해 유효 오퍼가 하나도 없는 극단 상황은 자유계약
        # 미체결 대신 원소속 최소 잔류로 처리해 로스터에서 선수가 사라지지 않게 한다.
        if not offers:
            offers.append((pending.home_tid, pending.fair, True))

        max_aav = max(aav for _tid, aav, _home in offers)
        best = None
        best_appeal = -1e9
        for tid, aav, is_home in offers:
            team = self.by_tid[tid]
            money = aav / max_aav
            play = (clamp(need_frac(team, p.pos) + 0.5, 0.0, 1.0)
                    if is_home else need_frac(team, p.pos))
            win = _win_score(self.rank[tid], len(self.teams))
            w = pending.weights
            appeal = (w[0] * money + w[1] * play + w[2] * win
                      + (TUNE["fa"]["loyalty"] if is_home else 0.0)
                      + self.rng.gauss(0, TUNE["fa"]["choice_noise"]))
            if appeal > best_appeal:
                best = (tid, aav, is_home)
                best_appeal = appeal

        to_tid, aav, is_home = best
        from_tid = p.team_id
        p.contract.salary = round(aav, 2)
        p.contract.years = pending.years
        p.contract.signing_bonus = round(
            aav * pending.years * TUNE["contract"]["signing_bonus_frac"], 2)
        p.fa_eligible_at = p.service_years + TUNE["fa"]["reelig"]
        signing = FASigning(
            p, from_tid, to_tid, p.fa_grade, round(aav, 2),
            round(pending.fair, 2), round(pending.comp, 2),
            len(offers) - 1, pending.weights,
        )
        self.report.signings.append(signing)

        if not is_home:
            home = self.by_tid[from_tid]
            destination = self.by_tid[to_tid]
            home.roster.remove(p)
            p.team_id = to_tid
            destination.roster.append(p)
            destination.budget = round(destination.budget - pending.comp, 2)
            home.budget = round(home.budget + pending.comp, 2)
            self.signed_count[to_tid] += 1
            self.spent[to_tid] += aav + pending.comp

        user_offered = mode == "offer"
        result = {
            "pid": p.pid,
            "name": p.name,
            "from_tid": from_tid,
            "to_tid": to_tid,
            "aav": round(aav, 2),
            "years": pending.years,
            "grade": p.fa_grade,
            "comp": round(pending.comp, 2),
            "accepted_user_offer": user_offered and to_tid == self.user_tid,
            "user_offered": user_offered,
            "mode": mode,
        }
        self.last_result = result
        self.index += 1
        self.pending = None
        self._prepare()
        return result

    def offer(self, aav: float) -> dict:
        return self._resolve("offer", aav)

    def pass_player(self) -> dict:
        return self._resolve("pass")

    def auto_resolve(self) -> dict:
        return self._resolve("auto")

    def auto_finish(self) -> None:
        while not self.complete:
            self.auto_resolve()

    def state(self) -> dict:
        if self.complete or self.pending is None:
            return {
                "active": False,
                "complete": True,
                "year": self.year,
                "declared": len(self.declared),
                "results": self._result_rows(),
                "released": [
                    {"tid": tid, "pid": player.pid, "name": player.name,
                     "pos": player.pos}
                    for tid, player in self.report.released
                ],
            }

        pending = self.pending
        p = pending.player
        team = self.by_tid[self.user_tid]
        user_is_home = self.user_tid == pending.home_tid
        max_offer = self._user_offer_limit(pending)
        recent_bat = p.season_bat
        recent_pit = p.season_pit
        return {
            "active": True,
            "complete": False,
            "year": self.year,
            "index": self.index + 1,
            "declared": len(self.declared),
            "player": {
                "pid": p.pid,
                "name": p.name,
                "age": p.age,
                "pos": p.pos,
                "grade": p.fa_grade,
                "team_id": pending.home_tid,
                "ovr": round(overall(p), 1),
                "salary": round(p.contract.salary, 2),
                "service_years": round(p.service_years, 1),
                "is_pitcher": p.is_pitcher,
                "bat_line": {
                    "avg": round(recent_bat.avg, 3),
                    "hr": recent_bat.hr,
                    "rbi": recent_bat.rbi,
                    "ops": round(recent_bat.ops, 3),
                },
                "pit_line": {
                    "era": round(recent_pit.era, 2),
                    "w": recent_pit.w,
                    "l": recent_pit.l,
                    "sv": recent_pit.sv,
                    "ip": round(recent_pit.ip, 1),
                },
            },
            "market": {
                "fair_aav": round(pending.fair, 2),
                "years": pending.years,
                "compensation": round(pending.comp, 2),
                "competitors": len([
                    offer for offer in pending.ai_offers
                    if offer[0] not in (self.user_tid, pending.home_tid)
                ]),
                "user_is_home": user_is_home,
                "user_need": round(need_frac(team, p.pos), 3),
                "user_budget": round(team.budget, 2),
                "user_spent": round(self.spent[self.user_tid], 2),
                "max_offer": round(max_offer, 2),
                "can_offer": max_offer >= TUNE["contract"]["min_salary"],
                "signing_limit": self.limit,
                "user_signings": self.signed_count[self.user_tid],
            },
            "last_result": self.last_result,
            "results": self._result_rows(),
        }

    def _result_rows(self) -> list[dict]:
        return [
            {
                "pid": signing.player.pid,
                "name": signing.player.name,
                "age": signing.player.age,
                "pos": signing.player.pos,
                "grade": signing.grade,
                "from_tid": signing.from_tid,
                "to_tid": signing.to_tid,
                "aav": signing.aav,
                "years": signing.player.contract.years,
                "comp": signing.comp,
            }
            for signing in self.report.signings
        ]
