"""웹 사용자 참여 오프시즌 상태머신.

콘솔 자동 경로는 변경하지 않는다. 웹 시즌 종료 시 에이징 후 사용자 트레이드,
FA 시장, 사용자 드래프트, 재정, 새 시즌 순으로 진행한다.
"""
from __future__ import annotations

from kbo.league.aging import offseason_tick
from kbo.league.draft_session import InteractiveDraft
from kbo.league.economy import offseason_finance_tick
from kbo.league.fa_session import InteractiveFAMarket
from kbo.league.postseason import PostseasonRunner
from kbo.league.trade_session import InteractiveTradeMarket


def _trade_report(market: InteractiveTradeMarket) -> dict:
    items = []
    for deal in market.report.trades:
        items.append(
            f"{deal.reb_tid} {deal.veteran.name}"
            f"({deal.veteran.age}세 {deal.veteran.pos}) ↔ "
            f"{deal.win_tid} {deal.prospects[0].name}"
            + (f"+지명권{[pick.round for pick in deal.picks]}R"
               if deal.picks else "")
        )
    for deal in market.user_trades:
        gave = ", ".join(getattr(asset, "name", f"{asset.round}R 지명권")
                         for asset in deal.user_gave)
        received = ", ".join(getattr(asset, "name", f"{asset.round}R 지명권")
                             for asset in deal.user_received)
        items.append(f"{deal.user_tid} [{gave}] ↔ {deal.other_tid} [{received}]")
    return {
        "stage": "트레이드",
        "items": items or ["성사된 트레이드 없음"],
    }


def _fa_report(market: InteractiveFAMarket) -> dict:
    moved = market.report.moved
    return {
        "stage": "FA",
        "items": [
            f"{move.player.name}({move.player.age}세 {move.grade}등급) "
            f"{move.from_tid}→{move.to_tid} "
            f"({move.player.contract.years}년·AAV {move.aav}억)"
            for move in moved
        ] + [
            f"잔류 {len(market.report.signings) - len(moved)}명 / "
            f"자격 {market.report.declared}명"
        ],
    }


def _draft_report(draft: InteractiveDraft, user_tid: str) -> dict:
    mine = [result for result in draft.results if result.tid == user_tid]
    return {
        "stage": "드래프트",
        "items": [
            f"{result.round}R {result.player.name}"
            f"({result.player.age}세 {result.player.pos})"
            for result in mine
        ] or ["우리 팀 지명 없음 (로스터 충원 불필요)"],
    }


def _begin_draft(session) -> None:
    standings = session.offseason_standings
    draft = InteractiveDraft(
        session.rng, session.teams, standings, session.year, session.user_tid)
    draft.advance_to_user()
    session.draft_session = draft
    session.last_draft_state = None
    if draft.complete:
        _complete_managed_offseason(session, draft)


def _complete_fa(session, market: InteractiveFAMarket) -> None:
    session.offseason_reports = list(session.offseason_reports) + [_fa_report(market)]
    session.last_fa_state = market.state()
    session.fa_session = None
    _begin_draft(session)


def _begin_fa(session) -> None:
    standings = session.offseason_standings
    session.fa_session = InteractiveFAMarket(
        session.rng, session.teams, standings, session.year, session.user_tid)
    session.last_fa_state = None
    if session.fa_session.complete:
        _complete_fa(session, session.fa_session)


def _complete_trade(session, market: InteractiveTradeMarket) -> None:
    session.offseason_reports = list(session.offseason_reports) + [_trade_report(market)]
    session.last_trade_state = market.state()
    session.trade_session = None
    _begin_fa(session)


def _begin_managed_offseason(session, standings) -> None:
    year = session.year
    aging = offseason_tick(session.rng, session.teams, year=year, draft_mode=True)
    session.offseason_reports = [{
        "stage": "에이징/은퇴",
        "items": [
            f"{team.tid} {player.name}({player.age}세) 은퇴"
            for team, player in aging.retired
        ] or ["은퇴 선수 없음"],
    }]
    session.offseason_standings = standings
    session.trade_session = InteractiveTradeMarket(
        session.rng, session.teams, standings, year, session.user_tid)
    session.last_trade_state = None
    session.fa_session = None
    session.last_fa_state = None
    session.draft_session = None
    session.last_draft_state = None


def _reset_user_roster_roles(session) -> None:
    """은퇴·이적 선수가 다음 시즌 라인업에 남지 않도록 새 로스터로 재편성한다."""
    team = session.user_team
    team.build_default_lineup()
    team.build_default_pitching()
    team.user_managed = True


def _complete_managed_offseason(session, draft: InteractiveDraft) -> None:
    final_state = draft.state()
    reports = list(session.offseason_reports)
    reports.append(_draft_report(draft, session.user_tid))

    finance = offseason_finance_tick(session.rng, session.teams, year=session.year)
    reports.append({
        "stage": "재정",
        "items": [
            f"경쟁균형세 캡 {finance.cap:.0f}억",
            f"우리 예산 {session.user_team.budget:.0f}억",
        ] + ([
            f"캡 초과 제재: {', '.join(tid for tid, _, _ in finance.tax_payers)}"
        ] if finance.tax_payers else []),
    })

    session.offseason_reports = reports
    session.last_draft_state = final_state
    session.draft_session = None
    session.offseason_standings = None
    _reset_user_roster_roles(session)
    session.year += 1
    session._new_season()


def apply_draft_management_patch() -> None:
    from web.backend.session import GameSession

    if getattr(GameSession, "_interactive_draft_patch", False):
        return

    original_init = GameSession.__init__
    original_advance = GameSession.advance
    original_load = GameSession.load

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.trade_session = None
        self.last_trade_state = None
        self.fa_session = None
        self.last_fa_state = None
        self.draft_session = None
        self.last_draft_state = None
        self.offseason_standings = None

    def patched_season_end(self):
        ranked = self.season.standings()
        my_rank = next(i for i, team in enumerate(ranked, 1)
                       if team.tid == self.user_tid)
        postseason = PostseasonRunner(
            ranked, self.rng, start_day=self.season.days_played).run()
        seed = {team.tid: i + 1 for i, team in enumerate(ranked)}
        self.postseason_summary = [
            f"{series.name}: {series.upper.name}({seed[series.upper.tid]}위) "
            f"{series.wins_u} - {series.wins_l} "
            f"{series.lower.name}({seed[series.lower.tid]}위) → "
            f"{series.winner.name}"
            for series in postseason.rounds
        ]
        self.postseason_summary.append(
            f"🏆 {postseason.champion.name} 한국시리즈 우승 "
            f"(정규 {seed[postseason.champion.tid]}위)")
        self.history.append({
            "year": self.year,
            "champion": postseason.champion.name,
            "my_rank": my_rank,
            "my_record": f"{self.user_team.wins}승 "
                         f"{self.user_team.ties}무 "
                         f"{self.user_team.losses}패",
        })
        _begin_managed_offseason(self, ranked)

    def patched_advance(self, unit: str) -> dict:
        if getattr(self, "trade_session", None) is not None:
            raise RuntimeError("트레이드 시장을 먼저 종료해야 합니다.")
        if getattr(self, "fa_session", None) is not None:
            raise RuntimeError("FA 시장 결정을 먼저 완료해야 합니다.")
        if getattr(self, "draft_session", None) is not None:
            raise RuntimeError("드래프트 지명을 먼저 완료해야 합니다.")
        return original_advance(self, unit)

    def require_trade(self) -> InteractiveTradeMarket:
        market = getattr(self, "trade_session", None)
        if market is None:
            raise LookupError("진행 중인 사용자 트레이드 시장이 없습니다.")
        return market

    def trade_state(self) -> dict:
        return require_trade(self).state()

    def trade_propose(self, other_tid: str, give_ids: list[str],
                      receive_ids: list[str]) -> dict:
        market = require_trade(self)
        result = market.propose(other_tid, give_ids, receive_ids)
        return {"result": result, "trade": market.state()}

    def trade_accept_counter(self) -> dict:
        market = require_trade(self)
        result = market.accept_counter()
        return {"result": result, "trade": market.state()}

    def trade_reject_counter(self) -> dict:
        market = require_trade(self)
        result = market.reject_counter()
        return {"result": result, "trade": market.state()}

    def trade_finish(self) -> dict:
        market = require_trade(self)
        result = market.finish()
        final_state = market.state()
        _complete_trade(self, market)
        return {
            "result": result,
            "trade": final_state,
            "trade_complete": True,
            "fa_active": self.fa_session is not None,
        }

    def require_fa(self) -> InteractiveFAMarket:
        market = getattr(self, "fa_session", None)
        if market is None:
            raise LookupError("진행 중인 사용자 FA 시장이 없습니다.")
        return market

    def fa_state(self) -> dict:
        return require_fa(self).state()

    def _fa_action(self, action: str, aav: float | None = None) -> dict:
        market = require_fa(self)
        if action == "offer":
            result = market.offer(aav)
        elif action == "pass":
            result = market.pass_player()
        elif action == "auto":
            result = market.auto_resolve()
        elif action == "auto_finish":
            market.auto_finish()
            result = market.last_result
        else:
            raise ValueError(f"알 수 없는 FA 작업입니다: {action}")
        state = market.state()
        completed = market.complete
        if completed:
            _complete_fa(self, market)
        return {
            "result": result,
            "fa": state,
            "fa_complete": completed,
            "draft_active": self.draft_session is not None,
        }

    def fa_offer(self, aav: float) -> dict:
        return _fa_action(self, "offer", aav)

    def fa_pass(self) -> dict:
        return _fa_action(self, "pass")

    def fa_auto(self) -> dict:
        return _fa_action(self, "auto")

    def fa_auto_finish(self) -> dict:
        return _fa_action(self, "auto_finish")

    def require_draft(self) -> InteractiveDraft:
        draft = getattr(self, "draft_session", None)
        if draft is None:
            raise LookupError("진행 중인 사용자 드래프트가 없습니다.")
        return draft

    def draft_state(self) -> dict:
        return require_draft(self).state()

    def draft_pick(self, player_pid: str) -> dict:
        draft = require_draft(self)
        selected = draft.pick(player_pid)
        state = draft.state()
        completed = draft.complete
        if completed:
            _complete_managed_offseason(self, draft)
        return {
            "selected": {
                "round": selected.round,
                "tid": selected.tid,
                "pid": selected.player.pid,
                "name": selected.player.name,
                "age": selected.player.age,
                "pos": selected.player.pos,
            },
            "draft": state,
            "season_started": completed,
        }

    def draft_auto_pick(self) -> dict:
        draft = require_draft(self)
        selected = draft.auto_pick()
        state = draft.state()
        completed = draft.complete
        if completed:
            _complete_managed_offseason(self, draft)
        return {
            "selected": {
                "round": selected.round,
                "tid": selected.tid,
                "pid": selected.player.pid,
                "name": selected.player.name,
                "age": selected.player.age,
                "pos": selected.player.pos,
            },
            "draft": state,
            "season_started": completed,
        }

    def patched_load(name: str = "save"):
        session = original_load(name)
        defaults = {
            "trade_session": None,
            "last_trade_state": None,
            "fa_session": None,
            "last_fa_state": None,
            "draft_session": None,
            "last_draft_state": None,
            "offseason_standings": None,
        }
        for attr, value in defaults.items():
            if not hasattr(session, attr):
                setattr(session, attr, value)
        return session

    GameSession.__init__ = patched_init
    GameSession._season_end = patched_season_end
    GameSession.advance = patched_advance
    GameSession.require_trade = require_trade
    GameSession.trade_state = trade_state
    GameSession.trade_propose = trade_propose
    GameSession.trade_accept_counter = trade_accept_counter
    GameSession.trade_reject_counter = trade_reject_counter
    GameSession.trade_finish = trade_finish
    GameSession.require_fa = require_fa
    GameSession.fa_state = fa_state
    GameSession.fa_offer = fa_offer
    GameSession.fa_pass = fa_pass
    GameSession.fa_auto = fa_auto
    GameSession.fa_auto_finish = fa_auto_finish
    GameSession.require_draft = require_draft
    GameSession.draft_state = draft_state
    GameSession.draft_pick = draft_pick
    GameSession.draft_auto_pick = draft_auto_pick
    GameSession.load = staticmethod(patched_load)
    GameSession._interactive_draft_patch = True
