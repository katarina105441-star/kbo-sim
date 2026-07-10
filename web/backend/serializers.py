"""엔진 객체 → JSON dict 변환 (표현 계층 — 게임 로직 없음)."""
from __future__ import annotations

from kbo.engine.game import GameResult
from kbo.league.aging import overall, potential
from kbo.models.player import Player
from kbo.models.team import Team

FORM_HOT, FORM_COLD = 0.8, -0.8


def _form_tag(p: Player) -> str:
    f = p.form_season + p.form_day
    return "hot" if f >= FORM_HOT else ("cold" if f <= FORM_COLD else "")


def player_brief(p: Player) -> dict:
    d = {
        "pid": p.pid, "name": p.name, "age": p.age, "pos": p.pos,
        "hand": f"{p.throws}투{p.bats}타", "team": p.team_id,
        "ovr": round(overall(p), 1),
        "salary": p.contract.salary, "years": p.contract.years,
        "inj_days": p.inj_days, "form": _form_tag(p), "stub": p.stub,
    }
    if p.is_pitcher:
        r = p.pit
        d["ratings"] = {"구속": r.velocity, "제구": r.control, "구위": r.stuff,
                        "스태미나": r.stamina, "변화구": r.breaking}
        l = p.season_pit
        d["line"] = {"G": l.g, "승": l.w, "패": l.l, "세": l.sv, "이닝": l.ip_str,
                     "ERA": f"{l.era:.2f}" if l.outs else "-", "탈삼진": l.so,
                     "WHIP": f"{l.whip:.2f}" if l.outs else "-"}
    else:
        r = p.bat
        d["ratings"] = {"컨택": r.contact, "파워": r.power, "선구": r.eye,
                        "주루": r.speed, "수비": r.fielding, "송구": r.arm}
        l = p.season_bat
        d["line"] = {"G": "-", "타율": f"{l.avg:.3f}" if l.ab else "-",
                     "홈런": l.hr, "타점": l.rbi, "도루": l.sb,
                     "출루": f"{l.obp:.3f}" if l.pa else "-",
                     "OPS": f"{l.ops:.3f}" if l.pa else "-"}
    for k, v in d["ratings"].items():
        d["ratings"][k] = round(v)
    return d


def player_detail(p: Player) -> dict:
    d = player_brief(p)
    d.update({
        "pot": round(potential(p), 1), "basis": p.basis, "est": p.est,
        "service_years": p.service_years, "fa_grade": p.fa_grade,
        "signing_bonus": p.contract.signing_bonus,
    })
    if p.is_pitcher:
        l = p.season_pit
        d["season_full"] = {"경기": l.g, "선발": l.gs, "승": l.w, "패": l.l,
                            "세이브": l.sv, "홀드": l.hld, "이닝": l.ip_str,
                            "탈삼진": l.so, "볼넷": l.bb, "피안타": l.h,
                            "자책": l.er, "ERA": f"{l.era:.2f}" if l.outs else "-",
                            "K/9": f"{l.k9:.1f}" if l.outs else "-"}
    else:
        l = p.season_bat
        d["season_full"] = {"타석": l.pa, "타수": l.ab, "안타": l.h, "2루타": l.b2,
                            "3루타": l.b3, "홈런": l.hr, "타점": l.rbi, "득점": l.r,
                            "볼넷": l.bb, "삼진": l.so, "도루": l.sb,
                            "타율": f"{l.avg:.3f}" if l.ab else "-",
                            "출루": f"{l.obp:.3f}" if l.pa else "-",
                            "장타": f"{l.slg:.3f}" if l.ab else "-"}
    return d


def team_summary(t: Team) -> dict:
    g = t.wins + t.losses + t.ties
    return {"tid": t.tid, "name": t.name, "city": t.city, "stadium": t.stadium,
            "games": g, "wins": t.wins, "ties": t.ties, "losses": t.losses,
            "pct": round(t.pct, 3), "budget": t.budget}


def standings_rows(ranked: list[Team]) -> list[dict]:
    rows = []
    top = ranked[0]
    for i, t in enumerate(ranked, 1):
        d = team_summary(t)
        d["rank"] = i
        d["gb"] = round(((top.wins - t.wins) + (t.losses - top.losses)) / 2, 1)
        rows.append(d)
    return rows


def roster(t: Team) -> dict:
    lineup_pids = [p.pid for p, _ in t.lineup]
    slots = {p.pid: s for p, s in t.lineup}
    return {
        "team": team_summary(t),
        "batters": [dict(player_brief(p),
                         order=(lineup_pids.index(p.pid) + 1
                                if p.pid in slots else None),
                         slot=slots.get(p.pid))
                    for p in sorted(t.batters, key=lambda x: -x.bat_overall)],
        "pitchers": [dict(player_brief(p),
                          role=("선발" if p in t.rotation else
                                "마무리" if p is t.closer else "불펜"))
                     for p in sorted(t.pitchers, key=lambda x: -x.pit_overall)],
    }


def boxscore(res: GameResult) -> dict:
    pid_name = {st.player.pid: st.player.name
                for s in ("away", "home") for st in res.stints[s]}
    dec = res.decisions
    out = {
        "away": {"tid": res.away.tid, "name": res.away.name, "runs": res.score[0]},
        "home": {"tid": res.home.tid, "name": res.home.name, "runs": res.score[1]},
        "line": res.line, "tie": res.tie, "innings": res.innings,
        "decisions": {"승": pid_name.get(dec["W"]), "패": pid_name.get(dec["L"]),
                      "세": pid_name.get(dec["SV"])},
        "batting": {}, "pitching": {},
    }
    for side in ("away", "home"):
        out["batting"][side] = [
            {"순": i, "이름": p.name, "포지션": slot, "타수": bl.ab, "안타": bl.h,
             "홈런": bl.hr, "타점": bl.rbi, "득점": bl.r, "볼넷": bl.bb + bl.hbp,
             "삼진": bl.so, "도루": bl.sb}
            for i, (p, slot, bl) in enumerate(res.box_bat[side], 1)]
        out["pitching"][side] = [
            {"이름": st.player.name, "이닝": st.line.ip_str, "투구": st.line.pitches,
             "피안타": st.line.h, "실점": st.line.r, "자책": st.line.er,
             "볼넷": st.line.bb + st.line.hbp, "삼진": st.line.so}
            for st in res.stints[side]]
    return out


def game_row(res: GameResult) -> dict:
    return {"away": res.away.tid, "home": res.home.tid,
            "score": list(res.score), "tie": res.tie,
            "watchable": bool(res.struct_events)}


# ---------- 관전 스트림 (DESIGN_WATCH.md) ----------
OUTCOME_KO = {"K": "삼진", "BB": "볼넷", "HBP": "사구", "1B": "안타",
              "2B": "2루타", "3B": "3루타", "HR": "홈런", "GO": "땅볼 아웃",
              "FO": "뜬공 아웃", "LO": "직선타 아웃", "DP": "병살타",
              "SF": "희생플라이", "E": "실책 출루"}


def _count_seq(rng, outcome: str, n_pitches: int) -> list[str]:
    """결과·투구수에 정합하는 볼카운트 연출 재구성 (B/S/F/X).

    엔진 밖 독립 rng — 엔진 난수 스트림 무접촉 (시드 결과 불변, DESIGN_WATCH §2).
    """
    n = max(1, n_pitches)
    if outcome == "BB":
        final, balls, strikes = "B", 3, min(2, max(0, n - 4))
    elif outcome == "K":
        final, strikes = "S", 2
        balls = min(3, max(0, n - 3))
    elif outcome == "HBP":
        final = "H"
        balls = min(3, max(0, n - 2)); strikes = 0
    else:                       # 인플레이
        final = "X"
        balls = min(3, n - 1); strikes = min(2, max(0, n - 1 - min(3, n - 1)))
    fouls = max(0, n - 1 - balls - strikes)
    priors = ["B"] * balls + ["S"] * strikes + ["F"] * fouls
    rng.shuffle(priors)
    # 파울은 2스트라이크 후에만 의미가 자연스러움 — 순서 보정 없이도 연출로 충분
    return priors[:n - 1] + [final]


def _pa_text(ev: dict) -> str:
    txt = f"{ev['inning']}회{ev['half']} {ev['batter']['name']}: " \
          f"{OUTCOME_KO.get(ev['outcome'], ev['outcome'])}"
    if ev["scored"]:
        a, h = ev["score"]                    # 타석 시작 시점 스코어
        if ev["half"] == "초":
            a += len(ev["scored"])
        else:
            h += len(ev["scored"])
        txt += f" — {', '.join(s['name'] for s in ev['scored'])} 홈인 ({a}:{h})"
    return txt


def watch_stream(res: GameResult) -> dict:
    """관전 스트림 직렬화. count_seq·text는 표현 편의 (Unity는 무시 가능)."""
    import random as _r
    names = {}
    for s in ("away", "home"):
        for p, _slot, _bl in res.box_bat[s]:
            names[p.pid] = p.name
        for st in res.stints[s]:
            names[st.player.pid] = st.player.name
    events = []
    for ev in res.struct_events:
        e = dict(ev)
        if e["t"] == "pa":
            e["count_seq"] = _count_seq(_r.Random(e["seed"]),
                                        e["outcome"], e["pitches"])
            e["text"] = _pa_text(e)
        elif e["t"] == "steal":
            e["text"] = (f"{e['inning']}회{e['half']} {e['runner']['name']} "
                         f"2루 도루 {'성공' if e['success'] else '실패'}")
        elif e["t"] == "pitch_change":
            e["text"] = f"{e['inning']}회{e['half']} {e['team']} 투수 교체: " \
                        f"{e['in']['name']}"
        events.append(e)
    return {
        "meta": {
            "away": {"tid": res.away.tid, "name": res.away.name},
            "home": {"tid": res.home.tid, "name": res.home.name},
            "names": names,
            "final": {"score": list(res.score), "innings": res.innings,
                      "tie": res.tie},
        },
        "events": events,
    }
