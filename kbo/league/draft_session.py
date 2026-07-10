"""중단·재개 가능한 사용자 참여 신인 드래프트.

기존 ``run_draft``의 풀 생성·스카우팅·BPA/Need/실링 평가식을 그대로 사용한다.
AI 지명은 자동으로 진행하고, 사용자 구단이 행사하는 유효 지명권에서만 멈춘다.
객체는 Player/Team 참조와 단순 커서만 보유해 pickle 저장·복원이 가능하다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.probability import TUNE, precompute_all
from ..models.player import Player
from ..models.team import Team
from .draft import (DraftPickResult, PIT_POS, build_pool, ceiling_bonus,
                    need_bonus, round_need_mult, scout)


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
        self.pool = build_pool(rng, teams, year)
        self.board = scout(rng, self.pool)
        self.order = [t.tid for t in reversed(standings)]
        self.by_tid = {t.tid: t for t in teams}
        self.target = {t.tid: 25 for t in teams}
        self.owner = {
            (pk.round, pk.original_tid): t.tid
            for t in teams for pk in t.draft_picks if pk.year == year
        }
        self.cursor = DraftCursor()
        self.results: list[DraftPickResult] = []
        self.complete = False
        self._precomputed = False

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
            precompute_all(p for t in self.teams for p in t.roster)
            self._precomputed = True

    def _current_slot(self) -> tuple[int, Team] | None:
        """로스터가 찬 슬롯을 건너뛰고 다음 실제 행사 팀을 반환한다."""
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
        """기존 run_draft와 동일하게 14야수/11투수 구성 보장 후보만 반환."""
        d = TUNE["draft"]
        n_bat = sum(1 for p in team.roster if not p.is_pitcher)
        n_pit = len(team.roster) - n_bat
        need_bat = n_bat < d["roster_bat"]
        need_pit = n_pit < d["roster_pit"]
        cands = [
            p for p in self.pool
            if (need_bat and not p.is_pitcher) or (need_pit and p.is_pitcher)
        ]
        return cands or list(self.pool)

    def _score(self, team: Team, player: Player, rnd: int) -> tuple[float, float]:
        raw_need = need_bonus(team, player.pos)
        score = (self.board[player.pid][0]
                 + raw_need * round_need_mult(rnd)
                 + ceiling_bonus(player, rnd))
        return score, raw_need

    def _best(self, team: Team, rnd: int) -> Player:
        best = None
        best_score = -1e9
        for player in self._eligible(team):
            score, _ = self._score(team, player, rnd)
            if score > best_score:
                best = player
                best_score = score
        return best

    def _select(self, team: Team, player: Player, rnd: int) -> DraftPickResult:
        if player not in self._eligible(team):
            raise ValueError("현재 로스터 구성상 지명할 수 없는 선수입니다.")
        self.pool.remove(player)
        scouted, true_val = self.board[player.pid]
        _, raw_need = self._score(team, player, rnd)
        player.team_id = team.tid
        team.roster.append(player)
        result = DraftPickResult(
            self.year, rnd, team.tid, player, scouted, true_val, raw_need)
        self.results.append(result)
        self._advance_cursor()
        return result

    def advance_to_user(self) -> None:
        """다음 사용자 지명권 또는 드래프트 종료까지 AI 지명을 진행한다."""
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
        player = next((p for p in self._eligible(team) if p.pid == player_pid), None)
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
        pct = rank / count
        if pct <= 0.10:
            return "A"
        if pct <= 0.30:
            return "B"
        if pct <= 0.60:
            return "C"
        if pct <= 0.85:
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
        ranked = sorted(eligible, key=lambda p: self.board[p.pid][0], reverse=True)
        rank_of = {p.pid: i + 1 for i, p in enumerate(ranked)}
        recommended = self._best(team, rnd)
        candidates = []
        for player in sorted(
                eligible,
                key=lambda p: self._score(team, p, rnd)[0],
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
                "scout_score": round(self.board[player.pid][0], 3),
                "need_bonus": round(raw_need, 3),
                "fit_score": round(fit, 3),
                "recommended": player.pid == recommended.pid,
                "type": "투수" if player.pos in PIT_POS else "야수",
            })
        needs = []
        for pos in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF",
                    "SP", "RP", "CL"):
            value = need_bonus(team, pos)
            if value > 0:
                needs.append({"pos": pos, "score": round(value, 3)})
        needs.sort(key=lambda x: x["score"], reverse=True)
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
