"""트레이드 검증 — 30시즌 (DESIGN_TRADE.md §6).

★핵심 2개: (1) gm_noise 객관 재측정 — 성사 거래를 중립 value_of로 다시 쟀을 때
대체로 등가인지 (한쪽 20~30% 손해 반복 = σ 과대). (2) 순위 순환 유지.
체인: 에이징 → 트레이드 → FA → 드래프트 → 재정 (풀 체인).
  python scripts/trade_check.py --seed 7
"""
import argparse
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick, overall
from kbo.league.draft import run_draft
from kbo.league.economy import init_market, offseason_finance_tick
from kbo.league.fa import run_fa_market, seed_service_years
from kbo.league.trade import run_trades
from kbo.league.season import SeasonRunner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    rng = random.Random(args.seed)

    rank_hist = defaultdict(list)
    champs = Counter()
    ps_appear = Counter()
    attempted = accepted = 0
    parity = []                      # min/max 객관 등가비 (거래별)
    with_picks = 0
    samples = []
    gamble = {}                      # pid -> (트레이드 시즌, 당시 OVR, 나이)
    gamble_out = []                  # (이름, 당시 OVR, 5년 후 OVR)

    for s in range(1, args.seasons + 1):
        season = SeasonRunner(teams, rng)
        season.run()
        st = season.standings()
        rank = {t.tid: i for i, t in enumerate(st, 1)}
        champs[st[0].tid] += 1
        for t in st[:5]:
            ps_appear[t.tid] += 1
        for t in teams:
            rank_hist[t.tid].append(rank[t.tid])
        # 유망주 도박 추적: 트레이드 5년 후 OVR
        for pid, (yr, ovr0, name) in list(gamble.items()):
            if s - yr == 5:
                p = next((x for t in teams for x in t.roster if x.pid == pid), None)
                gamble_out.append((name, ovr0, overall(p) if p else None))
                del gamble[pid]

        offseason_tick(rng, teams, year=s, draft_mode=True)
        rep = run_trades(rng, teams, st, year=s)
        attempted += rep.attempted
        accepted += len(rep.trades)
        for d in rep.trades:
            parity.append(min(d.obj_win, d.obj_reb) / max(d.obj_win, d.obj_reb))
            if d.picks:
                with_picks += 1
            for p in d.prospects:
                gamble[p.pid] = (s, overall(p), p.name)
            if len(samples) < 5:
                samples.append(f"{d.reb_tid}[{d.veteran.name} {d.veteran.age}세 "
                               f"{d.veteran.pos}]→{d.win_tid}({rank[d.win_tid]}위)"
                               f" | {d.prospects[0].name}({d.prospects[0].age}세)"
                               f"+픽{[pk.round for pk in d.picks]}"
                               f" | 객관 {d.obj_win:.0f}↔{d.obj_reb:.0f}억")
        run_fa_market(rng, teams, st, year=s)
        run_draft(rng, teams, st, year=s)
        offseason_finance_tick(rng, teams, year=s)

    print(f"=== 트레이드 검증 (풀 체인, {args.seasons}시즌, seed={args.seed}) ===\n")
    print("[★ 순위 순환] 팀별 우승·PS진출 (트레이드 도입 후에도 순환 유지?)")
    print(f"  {'팀':<5}{'우승':>4}{'PS진출':>6}{'평균순위':>7}{'최고':>4}{'최저':>4}")
    for t in sorted(teams, key=lambda t: -champs[t.tid]):
        r = rank_hist[t.tid]
        print(f"  {t.tid:<5}{champs[t.tid]:>4}{ps_appear[t.tid]:>6}"
              f"{sum(r)/len(r):>7.1f}{min(r):>4}{max(r):>4}")
    zero = [t.tid for t in teams if champs[t.tid] == 0]
    print(f"  최다 우승 {max(champs.values())}/{args.seasons} · 우승 0회 {zero or '없음'}")

    n = len(parity)
    print(f"\n[건수] 시도 {attempted} → 성사 {accepted} ({accepted/args.seasons:.1f}건/시즌,"
          f" 성사율 {accepted/attempted:.0%}) · 지명권 포함 {with_picks}건")
    if parity:
        sp = sorted(parity)
        lop = sum(1 for x in parity if x < 0.75)
        print(f"[★ 객관 등가 재측정] min/max 비 평균 {sum(parity)/n:.2f}"
              f" · p10 {sp[max(0, n//10 - 1)]:.2f} · 최저 {sp[0]:.2f}"
              f" · 한쪽 25%+ 손해 {lop}/{n}건 ({lop/n:.0%})")
    if gamble_out:
        ok = [g for g in gamble_out if g[2] is not None]
        hits = sum(1 for _, o0, o5 in ok if o5 - o0 >= 6)
        busts = sum(1 for _, o0, o5 in ok if o5 - o0 <= 0)
        gone = len(gamble_out) - len(ok)
        print(f"[유망주 도박] 추적 {len(gamble_out)}명: 성장 +6↑ {hits} ·"
              f" 정체/하락 {busts} · 리그 이탈(방출/은퇴) {gone}"
              f" — 대박과 bust 공존 {'✓' if hits and (busts or gone) else '?'}")
    print("\n[샘플]")
    for x in samples:
        print(f"  - {x}")


if __name__ == "__main__":
    main()
