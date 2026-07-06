"""콘솔 리포트 — 박스스코어/순위표/리그 집계 출력 (표현 계층: print는 여기서만)."""
from __future__ import annotations

from ..engine.game import GameResult
from ..league.season import SeasonRunner, LeagueTotals


def linescore_text(res: GameResult) -> str:
    n = len(res.line["away"])
    hdr = "  ".join(f"{i+1:>2}" for i in range(n))
    def row(side, name):
        cells = "  ".join("X " if v is None else f"{v:>2}" for v in res.line[side])
        total = res.score[0] if side == "away" else res.score[1]
        hits = sum(bl.h for _, _, bl in res.box_bat[side])
        errs = sum(bl.e for _, _, bl in res.box_bat[side])
        return f"{name:<14}{cells}  |{total:>3}{hits:>4}{errs:>3}"
    out = [f"{'팀':<13}{hdr}  |  R   H  E",
           row("away", res.away.name), row("home", res.home.name)]
    return "\n".join(out)


def boxscore_text(res: GameResult) -> str:
    lines = [linescore_text(res), ""]
    if res.tie:
        lines.append(f"** {res.innings}회 무승부 **")
    dec = res.decisions
    pid_name = {st.player.pid: st.player.name
                for s in ("away", "home") for st in res.stints[s]}
    if dec["W"]:
        parts = [f"승: {pid_name.get(dec['W'], '?')}", f"패: {pid_name.get(dec['L'], '?')}"]
        if dec["SV"]:
            parts.append(f"세: {pid_name.get(dec['SV'], '?')}")
        if dec["HLD"]:
            parts.append("홀: " + ", ".join(pid_name.get(h, "?") for h in dec["HLD"]))
        lines.append(" / ".join(parts))
    for side, team in (("away", res.away), ("home", res.home)):
        lines.append("")
        lines.append(f"[{team.name} 타자]")
        lines.append(f"{'타순':<4}{'이름':<16}{'포지션':<4}{'타수':>3}{'안타':>3}{'2루타':>4}{'홈런':>3}"
                     f"{'타점':>3}{'득점':>3}{'볼넷':>3}{'삼진':>3}{'도루':>3}")
        for i, (p, slot, bl) in enumerate(res.box_bat[side], 1):
            lines.append(f"{i:<5}{p.name:<17}{slot:<6}{bl.ab:>3}{bl.h:>4}{bl.b2:>4}{bl.hr:>4}"
                         f"{bl.rbi:>4}{bl.r:>4}{bl.bb + bl.hbp:>4}{bl.so:>4}{bl.sb:>4}")
        lines.append(f"[{team.name} 투수]")
        lines.append(f"{'이름':<16}{'이닝':>4}{'투구':>4}{'피안타':>4}{'실점':>3}{'자책':>3}"
                     f"{'볼넷':>3}{'삼진':>3}")
        for st in res.stints[side]:
            l = st.line
            lines.append(f"{st.player.name:<17}{l.ip_str:>5}{l.pitches:>5}{l.h:>5}{l.r:>4}"
                         f"{l.er:>4}{l.bb + l.hbp:>4}{l.so:>4}")
    return "\n".join(lines)


def events_text(res: GameResult) -> str:
    return "\n".join(res.events)


def standings_text(season: SeasonRunner) -> str:
    lines = [f"{'순위':<3}{'팀':<14}{'경기':>4}{'승':>4}{'무':>3}{'패':>4}{'승률':>7}"]
    for i, t in enumerate(season.standings(), 1):
        g = t.wins + t.losses + t.ties
        lines.append(f"{i:<4}{t.name:<15}{g:>4}{t.wins:>4}{t.ties:>3}{t.losses:>4}{t.pct:>8.3f}")
    return "\n".join(lines)


def league_report_text(tot: LeagueTotals) -> str:
    b, p = tot.bat, tot.pit
    rows = [
        ("리그 타율", f"{b.avg:.3f}"),
        ("리그 출루율", f"{b.obp:.3f}"),
        ("리그 장타율", f"{b.slg:.3f}"),
        ("리그 OPS", f"{b.ops:.3f}"),
        ("리그 ERA", f"{p.era:.2f}"),
        ("경기당 득점(팀)", f"{tot.r_per_game:.2f}"),
        ("경기당 홈런(팀)", f"{tot.hr_per_game:.2f}"),
        ("K/9", f"{p.k9:.2f}"),
        ("BB/9", f"{p.bb9:.2f}"),
        ("도루 성공률", f"{tot.sb_pct:.1%}"),
        ("팀당 병살", f"{b.gdp / 10:.0f}"),
        ("팀당 실책", f"{b.e / 10:.0f}"),
        ("비자책률", f"{(p.r - p.er) / p.r:.1%}" if p.r else "-"),
    ]
    return "\n".join(f"{k:<12}{v:>8}" for k, v in rows)


def postseason_text(ps, ranked) -> str:
    """포스트시즌 대진 결과. ps: PostseasonResult, ranked: 정규시즌 순위 리스트."""
    seed = {t.tid: i + 1 for i, t in enumerate(ranked)}
    lines = []
    for sr in ps.rounds:
        gtxt = " / ".join(f"{a}:{h}" + ("무" if tie else "")
                          for _, _, (a, h), tie in sr.games)
        adv = " (1승 어드밴티지)" if "와일드카드" in sr.name else ""
        lines.append(f"◆ {sr.name}: {sr.upper.name}({seed[sr.upper.tid]}위){adv} "
                     f"{sr.wins_u} - {sr.wins_l} {sr.lower.name}({seed[sr.lower.tid]}위)"
                     f"  →  {sr.winner.name} {'우승!' if '한국시리즈' in sr.name else '진출'}")
        lines.append(f"   경기: {gtxt}")
    lines.append(f"\n🏆 {ps.champion.name} — 한국시리즈 우승 "
                 f"(정규시즌 {seed[ps.champion.tid]}위)")
    return "\n".join(lines)


def ps_leaders_text(teams, top: int = 3) -> str:
    """포스트시즌 개인 기록 (정규시즌과 분리 집계된 ps_bat/ps_pit)."""
    bats = [(p, t) for t in teams for p in t.roster if p.ps_bat.pa >= 15]
    pits = [(p, t) for t in teams for p in t.roster if p.ps_pit.outs >= 9]
    lines = []

    def board(title, arr, key, fmt, reverse=True):
        rows = sorted(arr, key=key, reverse=reverse)[:top]
        if rows:
            lines.append(f"◆ PS {title}: " + " / ".join(
                f"{p.name}({t.tid}) {fmt(p)}" for p, t in rows))

    board("타율", bats, lambda x: x[0].ps_bat.avg, lambda p: f"{p.ps_bat.avg:.3f}")
    board("홈런", bats, lambda x: x[0].ps_bat.hr, lambda p: f"{p.ps_bat.hr}")
    board("타점", bats, lambda x: x[0].ps_bat.rbi, lambda p: f"{p.ps_bat.rbi}")
    board("ERA", pits, lambda x: -x[0].ps_pit.era,
          lambda p: f"{p.ps_pit.era:.2f} ({p.ps_pit.ip_str}이닝)")
    board("다승", pits, lambda x: x[0].ps_pit.w, lambda p: f"{p.ps_pit.w}승")
    return "\n".join(lines)


def leaders_text(teams, top: int = 5) -> str:
    bats = [(p, t) for t in teams for p in t.roster if p.season_bat.pa > 0]
    pits = [(p, t) for t in teams for p in t.roster if p.season_pit.outs > 0]
    q_pa = [x for x in bats if x[0].season_bat.pa >= 446]     # 규정타석 144*3.1
    q_ip = [x for x in pits if x[0].season_pit.outs >= 432]   # 규정이닝 144
    lines = []

    def board(title, arr, key, fmt, reverse=True):
        lines.append(f"◆ {title}")
        for p, t in sorted(arr, key=key, reverse=reverse)[:top]:
            lines.append(f"   {p.name:<14}{t.tid:<5}{fmt(p)}")

    board("타율", q_pa, lambda x: x[0].season_bat.avg, lambda p: f"{p.season_bat.avg:.3f}")
    board("홈런", bats, lambda x: x[0].season_bat.hr, lambda p: f"{p.season_bat.hr}")
    board("타점", bats, lambda x: x[0].season_bat.rbi, lambda p: f"{p.season_bat.rbi}")
    board("도루", bats, lambda x: x[0].season_bat.sb, lambda p: f"{p.season_bat.sb}")
    board("ERA", q_ip, lambda x: -x[0].season_pit.era, lambda p: f"{p.season_pit.era:.2f}")
    board("다승", pits, lambda x: x[0].season_pit.w, lambda p: f"{p.season_pit.w}승")
    board("세이브", pits, lambda x: x[0].season_pit.sv, lambda p: f"{p.season_pit.sv}")
    board("탈삼진", pits, lambda x: x[0].season_pit.so, lambda p: f"{p.season_pit.so}")
    return "\n".join(lines)
