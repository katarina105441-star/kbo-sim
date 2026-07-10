"""FA 보상선수 단계.

FA 계약 체결 시 기존 시장은 등급별 현금 전액(A 300%, B 200%, C 150%)을
먼저 이전한다. A/B등급에서 보상선수를 선택하면 원소속팀은 선수와 낮은 현금
(A 200%, B 100%)을 받고, 차액 100%는 영입팀으로 환급한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.probability import precompute_all
from ..models.player import Player
from ..models.team import Team
from .aging import overall, potential
from .contracts import value_of
from .economy import league_cap
from .fa import FASigning

PROTECTED_COUNT = {"A": 20, "B": 25}
FULL_CASH_MULT = {"A": 3.0, "B": 2.0, "C": 1.5}
PLAYER_CASH_MULT = {"A": 2.0, "B": 1.0}


@dataclass
class CompensationCase:
    signing: FASigning
    protected_ids: set[str] | None = None


class InteractiveFACompensation:
    def __init__(self, teams: list[Team], signings: list[FASigning],
                 year: int, user_tid: str):
        self.teams = teams
        self.by_tid = {team.tid: team for team in teams}
        self.year = year
        self.user_tid = user_tid.upper()
        self.cap = league_cap(year)
        self.cases: list[CompensationCase] = []
        self.index = 0
        self.complete = False
        self.last_result: dict | None = None
        self.results: list[dict] = []

        for signing in signings:
            if signing.to_tid == signing.from_tid:
                continue
            setattr(signing, "compensation_kind", "cash")
            setattr(signing, "compensation_player", None)
            setattr(signing, "compensation_cash", round(signing.comp, 2))
            if signing.grade in PROTECTED_COUNT:
                self.cases.append(CompensationCase(signing))
            else:
                self.results.append(self._cash_row(signing, automatic=True))

        self._advance_ai_cases()

    @property
    def current(self) -> CompensationCase | None:
        return self.cases[self.index] if self.index < len(self.cases) else None

    def _all_players(self, team: Team) -> list[Player]:
        return list(team.roster) + list(getattr(team, "minors", []))

    def _pool(self, signing: FASigning) -> list[Player]:
        destination = self.by_tid[signing.to_tid]
        return [p for p in self._all_players(destination)
                if p.pid != signing.player.pid]

    def _required(self, signing: FASigning) -> int:
        return min(PROTECTED_COUNT[signing.grade], len(self._pool(signing)))

    def _value(self, player: Player) -> float:
        return value_of(player, self.cap, role_pt=0.65, year=self.year)

    def _auto_protected(self, signing: FASigning) -> set[str]:
        pool = sorted(self._pool(signing), key=self._value, reverse=True)
        return {p.pid for p in pool[:self._required(signing)]}

    def _candidate_players(self, case: CompensationCase) -> list[Player]:
        protected = case.protected_ids or set()
        return sorted([p for p in self._pool(case.signing) if p.pid not in protected],
                      key=self._value, reverse=True)

    def _previous_salary(self, signing: FASigning) -> float:
        return signing.comp / FULL_CASH_MULT[signing.grade]

    def _player_cash(self, signing: FASigning) -> float:
        return round(self._previous_salary(signing)
                     * PLAYER_CASH_MULT[signing.grade], 2)

    def _cash_row(self, signing: FASigning, automatic: bool = False) -> dict:
        row = {
            "pid": signing.player.pid,
            "fa_name": signing.player.name,
            "grade": signing.grade,
            "from_tid": signing.from_tid,
            "to_tid": signing.to_tid,
            "kind": "cash",
            "cash": round(signing.comp, 2),
            "player": None,
            "automatic": automatic,
        }
        return row

    def _rebuild(self, team: Team) -> None:
        precompute_all(team.roster)
        team.build_default_lineup()
        team.build_default_pitching()

    def _choose_cash(self, case: CompensationCase, automatic: bool) -> dict:
        signing = case.signing
        setattr(signing, "compensation_kind", "cash")
        setattr(signing, "compensation_player", None)
        setattr(signing, "compensation_cash", round(signing.comp, 2))
        row = self._cash_row(signing, automatic)
        self.results.append(row)
        self.last_result = row
        return row

    def _choose_player(self, case: CompensationCase, player: Player,
                       automatic: bool) -> dict:
        signing = case.signing
        destination = self.by_tid[signing.to_tid]
        home = self.by_tid[signing.from_tid]
        if player not in self._candidate_players(case):
            raise ValueError("선택할 수 없는 보호선수 또는 보상 대상 선수입니다.")

        source_level = "active" if player in destination.roster else "minors"
        if source_level == "active":
            destination.roster.remove(player)
        else:
            destination.minors.remove(player)

        player.team_id = home.tid
        if source_level == "active" and len(home.roster) < 25:
            home.roster.append(player)
            receive_level = "active"
        else:
            home.minors.append(player)
            receive_level = "minors"

        full_cash = round(signing.comp, 2)
        player_cash = self._player_cash(signing)
        refund = round(full_cash - player_cash, 2)
        destination.budget = round(destination.budget + refund, 2)
        home.budget = round(home.budget - refund, 2)
        signing.comp = player_cash
        setattr(signing, "compensation_kind", "player")
        setattr(signing, "compensation_player", player)
        setattr(signing, "compensation_cash", player_cash)

        self._rebuild(destination)
        self._rebuild(home)
        row = {
            "pid": signing.player.pid,
            "fa_name": signing.player.name,
            "grade": signing.grade,
            "from_tid": signing.from_tid,
            "to_tid": signing.to_tid,
            "kind": "player",
            "cash": player_cash,
            "player": {
                "pid": player.pid,
                "name": player.name,
                "age": player.age,
                "pos": player.pos,
                "ovr": round(overall(player), 1),
                "level": receive_level,
            },
            "automatic": automatic,
        }
        self.results.append(row)
        self.last_result = row
        return row

    def _ai_decision(self, case: CompensationCase) -> dict:
        candidates = self._candidate_players(case)
        if not candidates:
            return self._choose_cash(case, automatic=True)
        best = candidates[0]
        refund = round(case.signing.comp - self._player_cash(case.signing), 2)
        # 보상선수 가치가 현금 선택 시 추가로 받을 차액보다 10% 이상 높을 때 지명.
        if self._value(best) >= refund * 1.10:
            return self._choose_player(case, best, automatic=True)
        return self._choose_cash(case, automatic=True)

    def _advance_ai_cases(self) -> None:
        while self.index < len(self.cases):
            case = self.cases[self.index]
            signing = case.signing
            if signing.to_tid == self.user_tid:
                return  # 사용자가 보호명단 제출
            case.protected_ids = self._auto_protected(signing)
            if signing.from_tid == self.user_tid:
                return  # 사용자가 선수/현금 선택
            self._ai_decision(case)
            self.index += 1
        self.complete = True

    def submit_protection(self, pids: list[str]) -> dict:
        case = self.current
        if case is None or case.signing.to_tid != self.user_tid:
            raise RuntimeError("사용자 보호선수 명단을 제출할 차례가 아닙니다.")
        pool_ids = {p.pid for p in self._pool(case.signing)}
        chosen = list(dict.fromkeys(pids))
        required = self._required(case.signing)
        if len(chosen) != required:
            raise ValueError(f"보호선수는 정확히 {required}명을 선택해야 합니다.")
        if any(pid not in pool_ids for pid in chosen):
            raise ValueError("보호 대상이 아닌 선수가 포함되어 있습니다.")
        case.protected_ids = set(chosen)
        result = self._ai_decision(case)
        self.index += 1
        self._advance_ai_cases()
        return result

    def auto_protect(self) -> dict:
        case = self.current
        if case is None or case.signing.to_tid != self.user_tid:
            raise RuntimeError("사용자 보호선수 명단을 제출할 차례가 아닙니다.")
        return self.submit_protection(list(self._auto_protected(case.signing)))

    def choose_player(self, pid: str) -> dict:
        case = self.current
        if case is None or case.signing.from_tid != self.user_tid:
            raise RuntimeError("사용자가 보상선수를 선택할 차례가 아닙니다.")
        player = next((p for p in self._candidate_players(case) if p.pid == pid), None)
        if player is None:
            raise ValueError("선택할 수 없는 보상선수입니다.")
        result = self._choose_player(case, player, automatic=False)
        self.index += 1
        self._advance_ai_cases()
        return result

    def choose_cash(self) -> dict:
        case = self.current
        if case is None or case.signing.from_tid != self.user_tid:
            raise RuntimeError("사용자가 보상 방식을 선택할 차례가 아닙니다.")
        result = self._choose_cash(case, automatic=False)
        self.index += 1
        self._advance_ai_cases()
        return result

    def auto_resolve(self) -> dict:
        case = self.current
        if case is None:
            raise RuntimeError("처리할 FA 보상 건이 없습니다.")
        if case.protected_ids is None:
            case.protected_ids = self._auto_protected(case.signing)
        result = self._ai_decision(case)
        self.index += 1
        self._advance_ai_cases()
        return result

    def auto_finish(self) -> None:
        while not self.complete:
            self.auto_resolve()

    def _player_row(self, player: Player, team: Team) -> dict:
        return {
            "pid": player.pid,
            "name": player.name,
            "age": player.age,
            "pos": player.pos,
            "ovr": round(overall(player), 1),
            "pot": round(potential(player), 1),
            "salary": round(player.contract.salary, 2),
            "level": "active" if player in team.roster else "minors",
            "value": round(self._value(player), 2),
        }

    def state(self) -> dict:
        if self.complete or self.current is None:
            return {
                "active": False,
                "complete": True,
                "year": self.year,
                "results": list(self.results),
                "last_result": self.last_result,
            }
        case = self.current
        signing = case.signing
        mode = "protect" if signing.to_tid == self.user_tid else "select"
        destination = self.by_tid[signing.to_tid]
        pool = self._pool(signing)
        candidates = self._candidate_players(case) if mode == "select" else []
        return {
            "active": True,
            "complete": False,
            "year": self.year,
            "index": self.index + 1,
            "total": len(self.cases),
            "mode": mode,
            "signing": {
                "pid": signing.player.pid,
                "name": signing.player.name,
                "grade": signing.grade,
                "from_tid": signing.from_tid,
                "to_tid": signing.to_tid,
                "aav": signing.aav,
                "full_cash": round(signing.comp, 2),
                "player_cash": self._player_cash(signing),
                "protection_count": self._required(signing),
            },
            "protectable": [self._player_row(p, destination) for p in
                            sorted(pool, key=self._value, reverse=True)],
            "candidates": [self._player_row(p, destination) for p in candidates],
            "recommended_protected": sorted(self._auto_protected(signing)),
            "results": list(self.results),
            "last_result": self.last_result,
        }
