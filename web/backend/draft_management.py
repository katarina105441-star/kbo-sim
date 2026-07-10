"""웹 GameSession에 사용자 참여 드래프트 상태머신을 연결한다.

콘솔의 자동 ``run_draft`` 경로는 변경하지 않는다. 웹 시즌 종료 시 에이징·트레이드·
FA까지 자동 진행한 뒤, 사용자 구단의 유효 지명권에서 멈추고 API 입력을 기다린다.
"""
from __future__ import annotations

from kbo.league.aging import offseason_tick
from kbo.league.draft_session import InteractiveDraft
from kbo.league.economy import offseason_finance_tick
from kbo.league.fa import run_fa_market
from kbo.league.postseason import PostseasonRunner
from kbo.league.trade import run_trades


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


def _begin_managed_offseason(session, standings) -> None:
    year = session.year
    reports = []

    aging = offseason_tick(session.rng, session.teams, year=year, draft_mode=True)
    reports.append({
        "stage": "에이징/은퇴",
        "items": [
            f"{team.tid} {player.name}({player.age}세) 은퇴"
            for team, player in aging.retired
        ] or ["은퇴 선수 없음"],
    })

    trades = run_trades(session.rng, session.teams, standings, year=year)
    reports.append({
        "stage": "트레이드",
        "items": [
            f"{deal.reb_tid} {deal.veteran.name}"
            f"({deal.veteran.age}세 {deal.veteran.pos}) ↔ "
            f"{deal.win_tid} {deal.prospects[0].name}"
            + (f"+지명권{[pick.round for pick in deal.picks]}R"
               if deal.picks else "")
            for deal in trades.trades
        ] or ["성사된 트레이드 없음"],
    })

    fa = run_fa_market(session.rng, session.teams, standings, year=year)
    moved = fa.moved
    reports.append({
        "stage": "FA",
        "items": [
            f"{move.player.name}({move.player.age}세 {move.grade}등급) "
            f"{move.from_tid}→{move.to_tid} (AAV {move.aav}억)"
            for move in moved
        ] + [f"잔류 {len(fa.signings) - len(moved)}명 / 자격 {fa.declared}명"],
    })

    draft = InteractiveDraft(
        session.rng, session.teams, standings, year, session.user_tid)
    draft.advance_to_user()
    session.offseason_reports = reports
    session.draft_session = draft
    session.last_draft_state = None

    if draft.complete:
        _complete_managed_offseason(session, draft)


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
        self.draft_session = None
        self.last_draft_state = None

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
        if getattr(self, "draft_session", None) is not None:
            raise RuntimeError("드래프트 지명을 먼저 완료해야 합니다.")
        return original_advance(self, unit)

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
        if not hasattr(session, "draft_session"):
            session.draft_session = None
        if not hasattr(session, "last_draft_state"):
            session.last_draft_state = None
        return session

    GameSession.__init__ = patched_init
    GameSession._season_end = patched_season_end
    GameSession.advance = patched_advance
    GameSession.require_draft = require_draft
    GameSession.draft_state = draft_state
    GameSession.draft_pick = draft_pick
    GameSession.draft_auto_pick = draft_auto_pick
    GameSession.load = staticmethod(patched_load)
    GameSession._interactive_draft_patch = True
