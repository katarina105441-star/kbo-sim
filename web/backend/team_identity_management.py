"""웹 세션·트레이드·FA 보상에 구단 성향을 연결한다.

드래프트와 FA 입찰은 공용 리그 엔진에서 직접 성향을 적용하므로 여기서 중복
패치하지 않는다.
"""
from __future__ import annotations

import math

from kbo.engine.probability import TUNE
from kbo.league.contracts import value_of
from kbo.league.team_identity import (
    effective_phase,
    ensure_team_identities,
    identity_of,
    trade_asset_multiplier,
)


def apply_team_identity_patch() -> None:
    from kbo.league import trade_session as trade_session_module
    from kbo.league.fa_compensation import InteractiveFACompensation
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

    # ---------- 트레이드: 운영 단계·선수 유형·스카우팅 정확도 ----------
    active_teams = {}
    active_rank = {}
    original_trade_init = trade_session_module.InteractiveTradeMarket.__init__

    def market_init(self, rng, teams, standings, year, user_tid):
        ensure_team_identities(teams)
        active_teams.clear()
        active_teams.update({team.tid: team for team in teams})
        active_rank.clear()
        active_rank.update({index: team for index, team in enumerate(standings, 1)})
        original_trade_init(self, rng, teams, standings, year, user_tid)

    def identity_phase(rank, n_teams):
        team = active_rank.get(rank)
        if team is None:
            contend = 1.0 - (rank - 1) / max(1, n_teams - 1)
            return "win" if contend >= 0.68 else "rebuild" if contend <= 0.32 else "mid"
        return effective_phase(team, rank, n_teams)

    def gm_value(self, tid, asset):
        key = (tid, id(asset))
        if key not in self.cache:
            trade_tune = TUNE["trade"]
            phase = self.phases.get(tid, "mid")
            discount = (trade_tune["disc_win"] if phase == "win" else
                        trade_tune["disc_reb"] if phase == "rebuild" else None)
            pick_mult = (trade_tune["pick_mult_win"] if phase == "win" else
                         trade_tune["pick_mult_reb"] if phase == "rebuild" else 1.0)
            objective = value_of(asset, self.cap, 1.0, self.year,
                                 discount=discount, pick_mult=pick_mult)
            team = active_teams.get(tid)
            if team is not None:
                objective *= trade_asset_multiplier(team, asset, phase)
                sigma = trade_tune["gm_noise"] / max(0.75, identity_of(team).scouting)
            else:
                sigma = trade_tune["gm_noise"]
            self.cache[key] = objective * math.exp(self.rng.gauss(0.0, sigma))
        return self.cache[key]

    trade_session_module.InteractiveTradeMarket.__init__ = market_init
    trade_session_module.team_phase = identity_phase
    GMView.value = gm_value

    # ---------- 보상선수: 보호명단도 구단 스타일에 맞춰 구성 ----------
    original_comp_value = InteractiveFACompensation._value

    def compensation_value(self, player):
        base = original_comp_value(self, player)
        team = self.by_tid.get(player.team_id)
        if team is None:
            return base
        strategy = identity_of(team).strategy
        phase = {"win_now": "win", "balanced": "mid", "rebuild": "rebuild"}[strategy]
        return base * trade_asset_multiplier(team, player, phase)

    InteractiveFACompensation._value = compensation_value

    GameSession._team_identity_patch = True
