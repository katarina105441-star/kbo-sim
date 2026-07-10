"""웹 게임의 드래프트·트레이드·FA AI에 구단 성향을 연결한다."""
from __future__ import annotations

import math

from kbo.engine.probability import TUNE
from kbo.league.aging import overall
from kbo.league.contracts import asset_war, value_of
from kbo.league.draft import ceiling_bonus, need_bonus, round_need_mult
from kbo.league.team_identity import (
    draft_fit_bonus,
    effective_phase,
    ensure_team_identities,
    fa_offer_multiplier,
    identity_of,
    scouting_sigma,
    trade_asset_multiplier,
)


def _scout_board(rng, pool, sigma: float) -> dict:
    board = {}
    for player in pool:
        true_value = asset_war(player, 1.0)
        observed = true_value * math.exp(rng.gauss(0.0, sigma))
        board[player.pid] = (observed, true_value)
    return board


def apply_team_identity_patch() -> None:
    from kbo.league import trade_session as trade_session_module
    from kbo.league.fa_compensation import InteractiveFACompensation
    from kbo.league.fa_session import InteractiveFAMarket
    from kbo.league.draft_session import InteractiveDraft
    from kbo.league.trade import GMView
    from web.backend.session import GameSession

    if getattr(GameSession, "_team_identity_patch", False):
        return

    # ---------- 세션 생성·저장 호환 ----------
    original_session_init = GameSession.__init__
    original_load = GameSession.load

    def session_init(self, *args, **kwargs):
        original_session_init(self, *args, **kwargs)
        ensure_team_identities(self.teams)

    def session_load(name: str = "save"):
        session = original_load(name)
        ensure_team_identities(session.teams)
        return session

    GameSession.__init__ = session_init
    GameSession.load = staticmethod(session_load)

    # ---------- 드래프트: 구단별 스카우팅 오차·선호 툴 ----------
    original_draft_init = InteractiveDraft.__init__
    original_draft_select = InteractiveDraft._select

    def draft_init(self, rng, teams, standings, year, user_tid):
        ensure_team_identities(teams)
        original_draft_init(self, rng, teams, standings, year, user_tid)
        base_sigma = TUNE["draft"]["scout_noise"]
        self.team_boards = {
            team.tid: _scout_board(rng, self.pool, scouting_sigma(team, base_sigma))
            for team in teams
        }
        self.board = self.team_boards[self.user_tid]

    def draft_score(self, team, player, rnd):
        raw_need = need_bonus(team, player.pos)
        board = self.team_boards.get(team.tid, self.board)
        score = (board[player.pid][0]
                 + raw_need * round_need_mult(rnd)
                 + ceiling_bonus(player, rnd)
                 + draft_fit_bonus(team, player, rnd))
        return score, raw_need

    def draft_select(self, team, player, rnd):
        previous = self.board
        self.board = self.team_boards.get(team.tid, previous)
        try:
            return original_draft_select(self, team, player, rnd)
        finally:
            self.board = self.team_boards.get(self.user_tid, previous)

    InteractiveDraft.__init__ = draft_init
    InteractiveDraft._score = draft_score
    InteractiveDraft._select = draft_select

    # ---------- 트레이드: 운영 단계·선수 유형·스카우팅 정확도 ----------
    active_teams = {}
    active_rank = {}
    original_trade_init = trade_session_module.InteractiveTradeMarket.__init__

    def market_init(self, rng, teams, standings, year, user_tid):
        ensure_team_identities(teams)
        active_teams.clear()
        active_teams.update({team.tid: team for team in teams})
        active_rank.clear()
        active_rank.update({i: team for i, team in enumerate(standings, 1)})
        original_trade_init(self, rng, teams, standings, year, user_tid)

    def identity_phase(rank, n_teams):
        team = active_rank.get(rank)
        if team is None:
            # 직접 함수 테스트 등 운영 컨텍스트가 없는 경우 기존 순위 기준과 동일한 경계.
            contend = 1.0 - (rank - 1) / max(1, n_teams - 1)
            return "win" if contend >= 0.68 else "rebuild" if contend <= 0.32 else "mid"
        return effective_phase(team, rank, n_teams)

    def gm_value(self, tid, asset):
        key = (tid, id(asset))
        if key not in self.cache:
            tr = TUNE["trade"]
            phase = self.phases.get(tid, "mid")
            discount = (tr["disc_win"] if phase == "win" else
                        tr["disc_reb"] if phase == "rebuild" else None)
            pick_mult = (tr["pick_mult_win"] if phase == "win" else
                         tr["pick_mult_reb"] if phase == "rebuild" else 1.0)
            objective = value_of(asset, self.cap, 1.0, self.year,
                                 discount=discount, pick_mult=pick_mult)
            team = active_teams.get(tid)
            if team is not None:
                objective *= trade_asset_multiplier(team, asset, phase)
                sigma = tr["gm_noise"] / max(0.75, identity_of(team).scouting)
            else:
                sigma = tr["gm_noise"]
            self.cache[key] = objective * math.exp(self.rng.gauss(0.0, sigma))
        return self.cache[key]

    trade_session_module.InteractiveTradeMarket.__init__ = market_init
    trade_session_module.team_phase = identity_phase
    GMView.value = gm_value

    # ---------- FA: 구단별 지출 적극성·선수 스타일 적합도 ----------
    original_ai_offers = InteractiveFAMarket._build_ai_offers

    def build_ai_offers(self, player, fair, comp, years):
        ensure_team_identities(self.teams)
        offers = original_ai_offers(self, player, fair, comp, years)
        adjusted = []
        for tid, aav, is_home in offers:
            if is_home:
                adjusted.append((tid, aav, is_home))
                continue
            team = self.by_tid[tid]
            offer = round(aav * fa_offer_multiplier(team, player), 2)
            if (self.spent[tid] + offer + comp
                    <= team.budget * TUNE["fa"]["spend_frac"]):
                adjusted.append((tid, offer, is_home))
        # 원소속팀 잔류 오퍼는 항상 남아 있다.
        return adjusted

    InteractiveFAMarket._build_ai_offers = build_ai_offers

    # ---------- 보상선수: 보호명단도 구단 스타일에 맞춰 구성 ----------
    original_comp_value = InteractiveFACompensation._value

    def compensation_value(self, player):
        base = original_comp_value(self, player)
        team = self.by_tid.get(player.team_id)
        if team is None:
            return base
        phase = effective_phase(team, self.teams.index(team) + 1, len(self.teams))
        return base * trade_asset_multiplier(team, player, phase)

    InteractiveFACompensation._value = compensation_value

    GameSession._team_identity_patch = True
