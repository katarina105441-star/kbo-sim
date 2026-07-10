"""FA 시장과 드래프트 사이에 보상선수 단계를 삽입한다."""
from __future__ import annotations

from kbo.league.fa_compensation import InteractiveFACompensation


def _compensation_report(session: InteractiveFACompensation) -> dict:
    items = []
    for result in session.results:
        if result["kind"] == "player":
            player = result["player"]
            items.append(
                f"{result['fa_name']}({result['grade']}등급) 보상: "
                f"{player['name']}({player['age']}세 {player['pos']}) + "
                f"{result['cash']:.2f}억"
            )
        else:
            items.append(
                f"{result['fa_name']}({result['grade']}등급) 보상: "
                f"현금 {result['cash']:.2f}억"
            )
    return {"stage": "FA 보상", "items": items or ["보상 대상 FA 이적 없음"]}


def apply_fa_compensation_patch() -> None:
    from web.backend import draft_management as dm
    from web.backend.session import GameSession

    if getattr(GameSession, "_fa_compensation_patch", False):
        return

    original_init = GameSession.__init__
    original_load = GameSession.load
    original_advance = GameSession.advance
    original_fa_methods = {
        name: getattr(GameSession, name)
        for name in ("fa_offer", "fa_pass", "fa_auto", "fa_auto_finish")
    }

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.compensation_session = None
        self.last_compensation_state = None

    def complete_compensation(session, compensation):
        final_state = compensation.state()
        session.offseason_reports = list(session.offseason_reports) + [
            _compensation_report(compensation)
        ]
        session.last_compensation_state = final_state
        session.compensation_session = None
        dm._begin_draft(session)

    def patched_complete_fa(session, market):
        session.offseason_reports = list(session.offseason_reports) + [dm._fa_report(market)]
        session.last_fa_state = market.state()
        session.fa_session = None
        compensation = InteractiveFACompensation(
            session.teams, market.report.signings, session.year, session.user_tid)
        session.compensation_session = compensation
        session.last_compensation_state = None
        if compensation.complete:
            complete_compensation(session, compensation)

    def patched_advance(self, unit: str):
        if getattr(self, "compensation_session", None) is not None:
            raise RuntimeError("FA 보상선수 결정을 먼저 완료해야 합니다.")
        return original_advance(self, unit)

    def require_compensation(self) -> InteractiveFACompensation:
        compensation = getattr(self, "compensation_session", None)
        if compensation is None:
            raise LookupError("진행 중인 FA 보상선수 단계가 없습니다.")
        return compensation

    def compensation_state(self):
        return require_compensation(self).state()

    def compensation_action(self, action: str, value=None):
        compensation = require_compensation(self)
        if action == "protect":
            result = compensation.submit_protection(value)
        elif action == "protect_auto":
            result = compensation.auto_protect()
        elif action == "player":
            result = compensation.choose_player(value)
        elif action == "cash":
            result = compensation.choose_cash()
        elif action == "auto":
            result = compensation.auto_resolve()
        elif action == "auto_finish":
            compensation.auto_finish()
            result = compensation.last_result
        else:
            raise ValueError(f"알 수 없는 FA 보상 작업입니다: {action}")
        state = compensation.state()
        completed = compensation.complete
        if completed:
            complete_compensation(self, compensation)
        return {
            "result": result,
            "compensation": state,
            "compensation_complete": completed,
            "draft_active": self.draft_session is not None,
        }

    def compensation_protect(self, pids):
        return compensation_action(self, "protect", pids)

    def compensation_auto_protect(self):
        return compensation_action(self, "protect_auto")

    def compensation_player(self, pid):
        return compensation_action(self, "player", pid)

    def compensation_cash(self):
        return compensation_action(self, "cash")

    def compensation_auto(self):
        return compensation_action(self, "auto")

    def compensation_auto_finish(self):
        return compensation_action(self, "auto_finish")

    def patched_load(name: str = "save"):
        session = original_load(name)
        if not hasattr(session, "compensation_session"):
            session.compensation_session = None
        if not hasattr(session, "last_compensation_state"):
            session.last_compensation_state = None
        return session

    def wrap_fa(name):
        original = original_fa_methods[name]

        def wrapped(self, *args, **kwargs):
            payload = original(self, *args, **kwargs)
            payload["compensation_active"] = (
                getattr(self, "compensation_session", None) is not None)
            return payload
        return wrapped

    dm._complete_fa = patched_complete_fa
    GameSession.__init__ = patched_init
    GameSession.advance = patched_advance
    GameSession.require_compensation = require_compensation
    GameSession.compensation_state = compensation_state
    GameSession.compensation_protect = compensation_protect
    GameSession.compensation_auto_protect = compensation_auto_protect
    GameSession.compensation_player = compensation_player
    GameSession.compensation_cash = compensation_cash
    GameSession.compensation_auto = compensation_auto
    GameSession.compensation_auto_finish = compensation_auto_finish
    for method_name in original_fa_methods:
        setattr(GameSession, method_name, wrap_fa(method_name))
    GameSession.load = staticmethod(patched_load)
    GameSession._fa_compensation_patch = True
