"""FA 자유계약 — 경매식 시장 (DESIGN_FA.md).

봉인식 단발 입찰 + 프리미엄: 구단 AI가 약점·경쟁력·운영 성향 기반 프리미엄을
얹어 오퍼하고, 선수가 돈+출전+우승 성향으로 선택한다.
등급별 보상금(A300/B200/C150%)이 이동 브레이크다.
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
from .team_identity import ensure_team_identities, fa_offer_multiplier


def seed_service_years(teams: list[Team]) -> None:
    stagger = int(TUNE["fa"]["reelig"])
    for team in teams:
        for player in team.roster:
            if player.service_years == 0.0:
                player.service_years = max(0.0, player.age - 20.0)
                player.fa_eligible_at = player.service_years + (player.age % stagger)


def eligible(player: Player) -> bool:
    tune = TUNE["fa"]
    return player.service_years >= max(tune["service_req"], player.fa_eligible_at)


def assign_grades(declared: list[Player]) -> None:
    ranked = sorted(declared, key=lambda player: player.contract.salary, reverse=True)
    count = len(ranked)
    for index, player in enumerate(ranked):
        player.fa_grade = "A" if index < count / 3 else ("B" if index < 2 * count / 3 else "C")


def need_frac(team: Team, pos: str) -> float:
    return need_bonus(team, pos) / TUNE["draft"]["need_max_bonus"]


def player_weights(rng: random.Random, player: Player) -> tuple[float, float, float]:
    tune = TUNE["fa"]
    money, play, win = tune["w_base"]
    if player.age >= tune["vet_age"]:
        win += tune["tilt"]
        play -= tune["tilt"]
    elif player.age <= tune["young_age"]:
        play += tune["tilt"]
        money -= tune["tilt"]
    weights = [max(0.02, value + rng.gauss(0, tune["w_noise"]))
               for value in (money, play, win)]
    total = sum(weights)
    return weights[0] / total, weights[1] / total, weights[2] / total


def fair_aav(player: Player, cap: float, year: int) -> float:
    contract_tune = TUNE["contract"]
    horizon_value = asset_war(player, 1.0) * dollar_per_war(cap, year)
    years = contract_years(player)
    return max(contract_tune["min_salary"],
               horizon_value / max(1, contract_tune["horizon"])
               * (1.0 if years <= 2 else 1.1))


def contract_years(player: Player) -> int:
    for age_high, years in TUNE["fa"]["contract_years"]:
        if player.age <= age_high:
            return years
    return 1


def compensation(player: Player) -> float:
    return player.contract.salary * TUNE["fa"]["comp"].get(player.fa_grade, 1.5)


@dataclass
class FASigning:
    player: Player
    from_tid: str
    to_tid: str
    grade: str
    aav: float
    fair: float
    comp: float
    n_offers: int
    w: tuple


@dataclass
class FAReport:
    declared: int = 0
    signings: list = field(default_factory=list)
    released: list = field(default_factory=list)

    @property
    def moved(self):
        return [signing for signing in self.signings
                if signing.to_tid != signing.from_tid]


def _win_score(rank: int, count: int) -> float:
    return 1.0 - (rank - 1) / max(1, count - 1)


def external_offer(team: Team, player: Player, fair: float,
                   rank: int, n_teams: int) -> float:
    """웹·콘솔 FA가 공유하는 구단 성향 반영 외부 오퍼."""
    tune = TUNE["fa"]
    need = need_frac(team, player.pos)
    premium = min(
        tune["overpay_cap"],
        tune["overpay_need"] * need
        + tune["overpay_win"] * _win_score(rank, n_teams),
    )
    return fair * (1.0 + premium) * fa_offer_multiplier(team, player)


def run_fa_market(rng: random.Random, teams: list[Team], standings: list[Team],
                  year: int) -> FAReport:
    tune = TUNE["fa"]
    ensure_team_identities(teams)
    cap = league_cap(year)
    rank = {team.tid: index for index, team in enumerate(standings, 1)}
    n_teams = len(teams)
    by_tid = {team.tid: team for team in teams}

    declared = [player for team in teams for player in team.roster if eligible(player)]
    report = FAReport(declared=len(declared))
    if not declared:
        return report
    assign_grades(declared)
    limit = max(1, len(declared) // tune["max_signings_divisor"])
    signed_count = {team.tid: 0 for team in teams}
    spent = {team.tid: 0.0 for team in teams}

    for player in sorted(declared, key=lambda item: asset_war(item, 1.0), reverse=True):
        home = by_tid[player.team_id]
        fair = fair_aav(player, cap, year)
        comp = compensation(player)
        years = contract_years(player)
        weights = player_weights(rng, player)

        offers = []
        if comp <= fair * years * tune["comp_tolerance"]:
            for team in teams:
                if team.tid == player.team_id:
                    continue
                if signed_count[team.tid] >= limit:
                    continue
                if need_frac(team, player.pos) < tune["need_min"]:
                    continue
                aav = external_offer(team, player, fair, rank[team.tid], n_teams)
                if spent[team.tid] + aav + comp > team.budget * tune["spend_frac"]:
                    continue
                offers.append((team, aav, False))
        offers.append((home, fair, True))

        max_aav = max(offer[1] for offer in offers)
        best = None
        best_appeal = -1.0
        for team, aav, is_home in offers:
            money = aav / max_aav
            play = (need_frac(team, player.pos) if not is_home else
                    clamp(need_frac(team, player.pos) + 0.5, 0.0, 1.0))
            win = _win_score(rank[team.tid], n_teams)
            appeal = (weights[0] * money + weights[1] * play + weights[2] * win
                      + (tune["loyalty"] if is_home else 0.0)
                      + rng.gauss(0, tune["choice_noise"]))
            if appeal > best_appeal:
                best, best_appeal = (team, aav, is_home), appeal

        destination, aav, is_home = best
        player.contract.salary = round(aav, 2)
        player.contract.years = years
        player.contract.signing_bonus = round(
            aav * years * TUNE["contract"]["signing_bonus_frac"], 2)
        player.fa_eligible_at = player.service_years + tune["reelig"]
        report.signings.append(FASigning(
            player, player.team_id, destination.tid, player.fa_grade,
            round(aav, 2), round(fair, 2), round(comp, 2), len(offers) - 1, weights))
        if not is_home:
            home.roster.remove(player)
            player.team_id = destination.tid
            destination.roster.append(player)
            destination.budget = round(destination.budget - comp, 2)
            home.budget = round(home.budget + comp, 2)
            signed_count[destination.tid] += 1
            spent[destination.tid] += aav + comp

    for team in teams:
        while len(team.roster) > 25:
            cut = min(team.roster, key=lambda player: asset_war(player, 0.5))
            team.roster.remove(cut)
            report.released.append((team.tid, cut))
    return report
