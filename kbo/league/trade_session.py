"""사용자 참여 트레이드 시장.

기존 ``trade.py``의 GMView·팀 단계·자산가치·AI 패키지 탐색을 재사용한다.
사용자 구단은 자동 거래에서 제외되며 선수/지명권 패키지를 직접 제안한다.
상대 AI는 주관 가치로 수락, 역제안, 거절 중 하나를 반환한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.probability import TUNE
from ..models.team import DraftPick, Team
from .aging import overall
from .contracts import value_of
from .economy import league_cap
from .trade import (GMView, TradeReport, TradeResult, _try_pair, mint_picks,
                    team_phase)


@dataclass
class UserTradeResult:
    year: int
    user_tid: str
    other_tid: str
    user_gave: list
    user_received: list
    source: str = "user"


class InteractiveTradeMarket:
    """오프시즌 사용자 트레이드 세션. pickle 저장·복원 가능."""

    def __init__(self, rng, teams: list[Team], standings: list[Team],
                 year: int, user_tid: str):
        self.rng = rng
        self.teams = teams
        self.standings = standings
        self.year = year
        self.user_tid = user_tid.upper()
        self.by_tid = {team.tid: team for team in teams}
        self.rank = {team.tid: i for i, team in enumerate(standings, 1)}
        self.phases = {
            team.tid: team_phase(self.rank[team.tid], len(teams)) for team in teams
        }
        self.gm = GMView(rng, league_cap(year), year, self.phases)
        self.report = TradeReport()
        self.user_trades: list[UserTradeResult] = []
        self.pending_counter: dict | None = None
        self.last_result: dict | None = None
        self.complete = False
        self.max_user_trades = max(1, int(TUNE["trade"]["max_per_team"]))

        mint_picks(teams, year)
        self._run_ai_only_market()

    @property
    def user_team(self) -> Team:
        return self.by_tid[self.user_tid]

    def _run_ai_only_market(self) -> None:
        """사용자 구단을 제외하고 기존 AI 트레이드 로직을 실행한다."""
        tr = TUNE["trade"]
        winnows = [team for team in self.standings
                   if team.tid != self.user_tid
                   and self.phases[team.tid] == "win"]
        rebuilds = [team for team in self.standings
                    if team.tid != self.user_tid
                    and self.phases[team.tid] == "rebuild"]
        done: dict[str, int] = {}
        for win in winnows:
            for reb in reversed(rebuilds):
                if len(self.report.trades) >= tr["max_league"]:
                    return
                if (done.get(win.tid, 0) >= tr["max_per_team"]
                        or done.get(reb.tid, 0) >= tr["max_per_team"]):
                    continue
                self.report.attempted += 1
                deal = _try_pair(self.gm, win, reb)
                if deal is None:
                    continue
                self._apply_ai_deal(deal)
                done[win.tid] = done.get(win.tid, 0) + 1
                done[reb.tid] = done.get(reb.tid, 0) + 1
                self.report.trades.append(deal)

    def _apply_ai_deal(self, deal: TradeResult) -> None:
        win = self.by_tid[deal.win_tid]
        reb = self.by_tid[deal.reb_tid]
        veteran = deal.veteran
        reb.roster.remove(veteran)
        veteran.team_id = win.tid
        win.roster.append(veteran)
        for player in deal.prospects:
            win.roster.remove(player)
            player.team_id = reb.tid
            reb.roster.append(player)
        for pick in deal.picks:
            win.draft_picks.remove(pick)
            reb.draft_picks.append(pick)

    @staticmethod
    def _asset_id(asset) -> str:
        if isinstance(asset, DraftPick):
            return f"D:{asset.year}:{asset.round}:{asset.original_tid}"
        return f"P:{asset.pid}"

    def _find_asset(self, team: Team, asset_id: str):
        if asset_id.startswith("P:"):
            pid = asset_id[2:]
            return next((p for p in team.roster if p.pid == pid), None)
        if asset_id.startswith("D:"):
            try:
                _kind, year, rnd, original = asset_id.split(":", 3)
                year, rnd = int(year), int(rnd)
            except (TypeError, ValueError):
                return None
            return next((pick for pick in team.draft_picks
                         if pick.year == year and pick.round == rnd
                         and pick.original_tid == original), None)
        return None

    def _resolve_assets(self, team: Team, asset_ids: list[str]) -> list:
        if not asset_ids:
            raise ValueError("최소 한 개의 자산을 선택해야 합니다.")
        if len(asset_ids) > 4:
            raise ValueError("한쪽 패키지는 최대 4개 자산까지 구성할 수 있습니다.")
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("같은 자산을 중복 선택할 수 없습니다.")
        assets = []
        for asset_id in asset_ids:
            asset = self._find_asset(team, asset_id)
            if asset is None:
                raise ValueError(f"보유하지 않은 자산입니다: {asset_id}")
            assets.append(asset)
        return assets

    def _validate_rosters(self, other: Team, user_give: list, user_receive: list) -> None:
        ug_players = sum(not isinstance(a, DraftPick) for a in user_give)
        ur_players = sum(not isinstance(a, DraftPick) for a in user_receive)
        user_after = len(self.user_team.roster) - ug_players + ur_players
        other_after = len(other.roster) - ur_players + ug_players
        if not 20 <= user_after <= 30:
            raise ValueError("거래 후 사용자 로스터는 20~30명이어야 합니다.")
        if not 20 <= other_after <= 30:
            raise ValueError("거래 후 상대 로스터는 20~30명이어야 합니다.")

    def _ai_ratio(self, other: Team, user_give: list, user_receive: list) -> tuple:
        ai_recv = sum(self.gm.value(other.tid, asset) for asset in user_give)
        ai_give = sum(self.gm.value(other.tid, asset) for asset in user_receive)
        ratio = ai_recv / max(0.01, ai_give)
        return ai_recv, ai_give, ratio

    def _user_estimate(self, user_give: list, user_receive: list) -> tuple:
        recv = sum(self.gm.objective(asset) for asset in user_receive)
        give = sum(self.gm.objective(asset) for asset in user_give)
        return give, recv

    def _make_counter(self, other: Team, user_give: list,
                      user_receive: list) -> tuple[list, list] | None:
        """부족분을 사용자 추가 자산 또는 상대 제공 자산 축소로 맞춘다."""
        threshold = 1.0 - TUNE["trade"]["tol"]
        counter_give = list(user_give)
        counter_receive = list(user_receive)
        chosen = {self._asset_id(asset) for asset in counter_give}

        # 먼저 사용자가 가진 가장 저가 자산부터 추가 요구한다.
        extras = [asset for asset in self.user_team.roster + self.user_team.draft_picks
                  if self._asset_id(asset) not in chosen]
        extras.sort(key=lambda asset: self.gm.value(other.tid, asset))
        for asset in extras:
            if len(counter_give) >= 4:
                break
            counter_give.append(asset)
            _recv, _give, ratio = self._ai_ratio(other, counter_give, counter_receive)
            if ratio >= threshold:
                return counter_give, counter_receive

        # 추가 요구로 안 되면 상대가 내주는 자산 중 AI가 가장 아끼는 자산부터 뺀다.
        while len(counter_receive) > 1:
            remove = max(counter_receive,
                         key=lambda asset: self.gm.value(other.tid, asset))
            counter_receive.remove(remove)
            _recv, _give, ratio = self._ai_ratio(other, counter_give, counter_receive)
            if ratio >= threshold:
                return counter_give, counter_receive
        return None

    def propose(self, other_tid: str, give_asset_ids: list[str],
                receive_asset_ids: list[str]) -> dict:
        if self.complete:
            raise RuntimeError("트레이드 시장이 이미 종료됐습니다.")
        if len(self.user_trades) >= self.max_user_trades:
            raise RuntimeError("이번 오프시즌 사용자 트레이드 한도를 모두 사용했습니다.")
        other_tid = other_tid.upper()
        if other_tid == self.user_tid or other_tid not in self.by_tid:
            raise ValueError("유효한 상대 구단을 선택해야 합니다.")
        other = self.by_tid[other_tid]
        user_give = self._resolve_assets(self.user_team, give_asset_ids)
        user_receive = self._resolve_assets(other, receive_asset_ids)
        self._validate_rosters(other, user_give, user_receive)
        self.pending_counter = None

        ai_recv, ai_give, ratio = self._ai_ratio(other, user_give, user_receive)
        objective_give, objective_receive = self._user_estimate(user_give, user_receive)
        threshold = 1.0 - TUNE["trade"]["tol"]

        if ratio >= threshold:
            result = self._execute(other, user_give, user_receive, "accepted")
            result.update({"ai_ratio": round(ratio, 3),
                           "objective_give": round(objective_give, 2),
                           "objective_receive": round(objective_receive, 2)})
            return result

        # 가치가 일정 범위 안이면 AI가 역제안한다. 너무 차이나면 즉시 거절.
        if ratio >= 0.55:
            counter = self._make_counter(other, user_give, user_receive)
            if counter is not None:
                counter_give, counter_receive = counter
                self._validate_rosters(other, counter_give, counter_receive)
                self.pending_counter = {
                    "other_tid": other.tid,
                    "give_ids": [self._asset_id(a) for a in counter_give],
                    "receive_ids": [self._asset_id(a) for a in counter_receive],
                }
                payload = {
                    "status": "counter",
                    "message": f"{other.name}이(가) 조건을 조정해 역제안했습니다.",
                    "counter": self._package_payload(
                        other, counter_give, counter_receive),
                    "ai_ratio": round(ratio, 3),
                    "objective_give": round(objective_give, 2),
                    "objective_receive": round(objective_receive, 2),
                }
                self.last_result = payload
                return payload

        payload = {
            "status": "rejected",
            "message": f"{other.name}이(가) 가치 차이가 크다며 제안을 거절했습니다.",
            "ai_ratio": round(ratio, 3),
            "objective_give": round(objective_give, 2),
            "objective_receive": round(objective_receive, 2),
        }
        self.last_result = payload
        return payload

    def accept_counter(self) -> dict:
        if self.pending_counter is None:
            raise RuntimeError("수락할 역제안이 없습니다.")
        counter = self.pending_counter
        other = self.by_tid[counter["other_tid"]]
        user_give = self._resolve_assets(self.user_team, counter["give_ids"])
        user_receive = self._resolve_assets(other, counter["receive_ids"])
        self._validate_rosters(other, user_give, user_receive)
        self.pending_counter = None
        return self._execute(other, user_give, user_receive, "counter_accepted")

    def reject_counter(self) -> dict:
        if self.pending_counter is None:
            raise RuntimeError("거절할 역제안이 없습니다.")
        other_tid = self.pending_counter["other_tid"]
        self.pending_counter = None
        payload = {
            "status": "counter_rejected",
            "message": f"{self.by_tid[other_tid].name}의 역제안을 거절했습니다.",
        }
        self.last_result = payload
        return payload

    def _execute(self, other: Team, user_give: list,
                 user_receive: list, status: str) -> dict:
        for asset in user_give:
            self._move_asset(asset, self.user_team, other)
        for asset in user_receive:
            self._move_asset(asset, other, self.user_team)
        record = UserTradeResult(
            self.year, self.user_tid, other.tid,
            list(user_give), list(user_receive))
        self.user_trades.append(record)
        payload = {
            "status": status,
            "message": f"{other.name}과(와) 트레이드가 성사됐습니다.",
            "trade": self._package_payload(other, user_give, user_receive),
            "trades_remaining": self.max_user_trades - len(self.user_trades),
        }
        self.last_result = payload
        return payload

    def _move_asset(self, asset, source: Team, destination: Team) -> None:
        if isinstance(asset, DraftPick):
            source.draft_picks.remove(asset)
            destination.draft_picks.append(asset)
        else:
            source.roster.remove(asset)
            asset.team_id = destination.tid
            destination.roster.append(asset)

    def finish(self) -> dict:
        if self.complete:
            raise RuntimeError("트레이드 시장이 이미 종료됐습니다.")
        self.pending_counter = None
        self.complete = True
        payload = {
            "status": "complete",
            "message": "사용자 트레이드 시장을 종료했습니다.",
            "user_trades": len(self.user_trades),
        }
        self.last_result = payload
        return payload

    def _asset_payload(self, asset, viewer_tid: str) -> dict:
        if isinstance(asset, DraftPick):
            objective = value_of(asset, league_cap(self.year), 1.0, self.year)
            return {
                "id": self._asset_id(asset), "type": "pick",
                "name": f"{asset.year}년 {asset.round}라운드 지명권",
                "round": asset.round, "year": asset.year,
                "original_tid": asset.original_tid,
                "estimated_value": round(objective, 2),
            }
        return {
            "id": self._asset_id(asset), "type": "player",
            "pid": asset.pid, "name": asset.name, "age": asset.age,
            "pos": asset.pos, "ovr": round(overall(asset), 1),
            "salary": round(asset.contract.salary, 2),
            "years": asset.contract.years,
            "estimated_value": round(self.gm.objective(asset), 2),
            "inj_days": asset.inj_days,
        }

    def _team_assets(self, team: Team) -> dict:
        players = sorted(team.roster, key=lambda p: overall(p), reverse=True)
        picks = sorted(team.draft_picks, key=lambda p: (p.year, p.round, p.original_tid))
        return {
            "tid": team.tid,
            "name": team.name,
            "phase": self.phases[team.tid],
            "rank": self.rank[team.tid],
            "roster_count": len(team.roster),
            "players": [self._asset_payload(p, self.user_tid) for p in players],
            "picks": [self._asset_payload(p, self.user_tid) for p in picks],
        }

    def _package_payload(self, other: Team, user_give: list,
                         user_receive: list) -> dict:
        return {
            "other_tid": other.tid,
            "other_name": other.name,
            "user_gives": [self._asset_payload(a, self.user_tid) for a in user_give],
            "user_receives": [self._asset_payload(a, self.user_tid) for a in user_receive],
        }

    def state(self) -> dict:
        teams = [self._team_assets(team) for team in self.standings
                 if team.tid != self.user_tid]
        counter = None
        if self.pending_counter is not None:
            other = self.by_tid[self.pending_counter["other_tid"]]
            give = [self._find_asset(self.user_team, asset_id)
                    for asset_id in self.pending_counter["give_ids"]]
            receive = [self._find_asset(other, asset_id)
                       for asset_id in self.pending_counter["receive_ids"]]
            if all(give) and all(receive):
                counter = self._package_payload(other, give, receive)
        return {
            "active": not self.complete,
            "complete": self.complete,
            "year": self.year,
            "user_tid": self.user_tid,
            "user_phase": self.phases[self.user_tid],
            "user": self._team_assets(self.user_team),
            "teams": teams,
            "max_user_trades": self.max_user_trades,
            "user_trades_count": len(self.user_trades),
            "trades_remaining": self.max_user_trades - len(self.user_trades),
            "pending_counter": counter,
            "last_result": self.last_result,
            "ai_trades": [
                {
                    "win_tid": deal.win_tid, "reb_tid": deal.reb_tid,
                    "veteran": deal.veteran.name,
                    "prospects": [p.name for p in deal.prospects],
                    "picks": [p.round for p in deal.picks],
                }
                for deal in self.report.trades
            ],
            "user_trades": [
                self._package_payload(
                    self.by_tid[deal.other_tid], deal.user_gave, deal.user_received)
                for deal in self.user_trades
            ],
        }
