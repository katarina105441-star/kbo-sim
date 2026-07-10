"""중단·재개 가능한 사용자 참여 신인 드래프트.

공용 ``run_draft``와 동일한 구단별 스카우팅 보드·BPA/Need/성향 평가식을 사용한다.
AI 지명은 자동으로 진행하고, 사용자 구단이 행사하는 유효 지명권에서만 멈춘다.
객체는 Player/Team 참조와 단순 커서만 보유해 pickle 저장·복원이 가능하다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.probability import TUNE, precompute_all
from ..models.player import Player
from ..models.team import Team
from .draft import (DraftPickResult, PIT_POS, build_pool, ceiling_bonus,
                    need_bonus, round_need_mult, scout, scout_for_team)
from .team_identity import draft_fit_bonus, ensure_team_identities


@dataclass
class DraftCursor:
    round: int = 1
    slot_index: int = 0


class InteractiveDraft:
    def __init__(self, rng, teams: list[Team], standings: list[Team],
                 year: int, user_tid: str):
        self.rng = rng
        self.teams = teams
        self.year = year
        self.user_tid = user_tid.upper()
        ensure_team_identities(teams)
        self.pool = build_pool(rng, teams, year)
        scout(rng, self.pool)  # 공용 자동 경로와 RNG 소비 순서 일치
        self.team_boards = {
            team.tid: scout_for_team(rng, self.pool, team) for team in teams
        }
        self.board = self.team_boards[self.user_tid]
        self.order = [team.tid for team in reversed(standings)]
        self.by_tid = {team.tid: team for team in teams}
        self.target = {team.tid: 25 for team in teams}
        self.owner = {
            (pick.round, pick.original_tid): team.tid
            for team in teams for pick in team.draft_picks if pick.year == year
        }
        self.cursor = DraftCursor()
        self.results: list[DraftPickResult] = []
        self.complete = False
        self._precomputed = False

    def _team_board(self, team: Team) -> dict:
        """기존 저장 파일의 단일 보드도 안전하게 이어간다."""
        return getattr(self, "team_boards", {}).get(team.tid, self.board)

    def _advance_cursor(self) -> None:
        self.cursor.slot_index += 1
        if self.cursor.slot_index >= len(self.order):
            self.cursor.slot_index = 0
            self.cursor.round += 1
        if self.cursor.round > TUNE["draft"]["rounds"] or not self.pool:
            self._finish()

    def _finish(self) -> None:
        self.complete = True
        if not self._precomputed:
            precompute_all(player for team in self.teams for player in team.roster)
            self._precomputed = True

    def _current_slot(self) -> tuple[int, Team] | None:
        while not self.complete:
            if self.cursor.round > TUNE["draft"]["rounds"] or not self.pool:
                self._finish()
                return None
            original_tid = self.order[self.cursor.slot_index]
            owner_tid = self.owner.get((self.cursor.round, original_tid), original_tid)
            team = self.by_tid[owner_tid]
            if len(team.roster) >= self.target[team.tid]:
                self._advance_cursor()
                continue
            return self.cursor.round, team
        return None

    def _eligible(self, team: Team) -> list[Player]:
        d = TUNE["draft"]
        n_batters = sum(1 for player in team.roster if not player.is_pitcher)
        n_pitchers = len(team.roster) - n_batters
        need_batter = n_batters < d["roster_bat"]
        need_pitcher = n_pitchers < d["roster_pit"]
        candidates = [
            player for player in self.pool
            if (need_batter and not player.is_pitcher)
            or (need_pitcher and player.is_pitcher)
        ]
        return candidates or list(self.pool)

    def _score(self, team: Team, player: Player, rnd: int) -> tuple[float, float]:
        raw_need = need_bonus(team, player.pos)
        board = self._team_board(team)
        score = (board[player.pid][0]
                 + raw_need * round_need_mult(rnd)
                 + ceiling_bonus(player, rnd)
                 + draft_fit_bonus(team, player, rnd))
        return score, raw_need

    def _best(self, team: Team, rnd: int) -> Player:
        best = None
        best_score = -1e9
        for player in self._eligible(team):
            score, _need = self._score(team, player, rnd)
            if score > best_score:
                best = player
                best_score = score
        return best

    def _select(self, team: Team, player: Player, rnd: int) -> DraftPickResult:
        if player not in self._eligible(team):
            raise ValueError("현재 로스터 구성상 지명할 수 없는 선수입니다.")
        self.pool.remove(player)
        scouted, true_value = self._team_board(team)[player.pid]
        _score, raw_need = self._score(team, player, rnd)
        player.team_id = team.tid
        team.roster.append(player)
        result = DraftPickResult(
            self.year, rnd, team.tid, player, scouted, true_value, raw_need)
        self.results.append(result)
        self._advance_cursor()
        return result

    def advance_to_user(self) -> None:
        while not self.complete:
            current = self._current_slot()
            if current is None:
                return
            rnd, team = current
            if team.tid == self.user_tid:
                return
            self._select(team, self._best(team, rnd), rnd)

    @property
    def user_turn(self) -> bool:
        current = self._current_slot()
        return bool(current and current[1].tid == self.user_tid)

    def pick(self, player_pid: str) -> DraftPickResult:
        current = self._current_slot()
        if current is None:
            raise RuntimeError("드래프트가 이미 종료되었습니다.")
        rnd, team = current
        if team.tid != self.user_tid:
            raise RuntimeError("현재는 사용자 구단의 지명 차례가 아닙니다.")
        player = next((candidate for candidate in self._eligible(team)
                       if candidate.pid == player_pid), None)
        if player is None:
            raise ValueError("현재 지명 가능한 유망주가 아닙니다.")
        result = self._select(team, player, rnd)
        self.advance_to_user()
        return result

    def auto_pick(self) -> DraftPickResult:
        current = self._current_slot()
        if current is None:
            raise RuntimeError("드래프트가 이미 종료되었습니다.")
        rnd, team = current
        if team.tid != self.user_tid:
            raise RuntimeError("현재는 사용자 구단의 지명 차례가 아닙니다.")
        result = self._select(team, self._best(team, rnd), rnd)
        self.advance_to_user()
        return result

    @staticmethod
    def _grade(rank: int, count: int) -> str:
        if count <= 1:
            return "A"
        percentile = rank / count
        if percentile <= 0.10:
            return "A"
        if percentile <= 0.30:
            return "B"
        if percentile <= 0.60:
            return "C"
        if percentile <= 0.85:
            return "D"
        return "E"

    def state(self) -> dict:
        current = self._current_slot()
        if current is None:
            return {
                "active": False,
                "complete": True,
                "year": self.year,
                "results": self._result_rows(),
            }
        rnd, team = current
        eligible = self._eligible(team)
        board = self._team_board(team)
        ranked = sorted(eligible, key=lambda player: board[player.pid][0], reverse=True)
        rank_of = {player.pid: index + 1 for index, player in enumerate(ranked)}
        recommended = self._best(team, rnd)
        candidates = []
        for player in sorted(
                eligible,
                key=lambda candidate: self._score(team, candidate, rnd)[0],
                reverse=True):
            fit, raw_need = self._score(team, player, rnd)
            candidates.append({
                "pid": player.pid,
                "name": player.name,
                "age": player.age,
                "pos": player.pos,
                "bats": player.bats,
                "throws": player.throws,
                "scout_grade": self._grade(rank_of[player.pid], len(ranked)),
                "scout_rank": rank_of[player.pid],
                "scout_score": round(board[player.pid][0], 3),
                "need_bonus": round(raw_need, 3),
                "fit_score": round(fit, 3),
                "recommended": player.pid == recommended.pid,
                "type": "투수" if player.pos in PIT_POS else "야수",
            })
        needs = []
        for position in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF",
                         "SP", "RP", "CL"):
            value = need_bonus(team, position)
            if value > 0:
                needs.append({"pos": position, "score": round(value, 3)})
        needs.sort(key=lambda row: row["score"], reverse=True)
        return {
            "active": True,
            "complete": False,
            "year": self.year,
            "round": rnd,
            "overall_pick": len(self.results) + 1,
            "team": {"tid": team.tid, "name": team.name},
            "user_turn": team.tid == self.user_tid,
            "remaining_pool": len(self.pool),
            "roster_count": len(team.roster),
            "candidates": candidates,
            "needs": needs[:5],
            "results": self._result_rows(),
        }

    def _result_rows(self) -> list[dict]:
        return [
            {
                "round": result.round,
                "tid": result.tid,
                "pid": result.player.pid,
                "name": result.player.name,
                "age": result.player.age,
                "pos": result.player.pos,
                "scout_score": round(result.scouted, 3),
            }
            for result in self.results
        ]
