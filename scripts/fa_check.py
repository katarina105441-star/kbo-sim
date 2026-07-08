"""FA 검증 — 30시즌 (DESIGN_FA.md §7). ★최우선: 순위 순환 균형.

FA(부익부)와 드래프트(역순=약팀 유리)의 균형 확인:
  python scripts/fa_check.py --seed 7            # FA 포함 체인
  python scripts/fa_check.py --seed 7 --no-fa    # FA 제외 기준선 (전/후 비교)
지표: 팀별 우승/PS진출 분포(편중), FA 영입 팀별 분포(독식), 등급 이동률,
FM 서사 샘플, 오버페이. RNG 함정 → 4시드+로 돌려 판단할 것.
"""
import argparse
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick
from kbo.league.draft import run_draft
from kbo.league.economy import init_market, offseason_finance_tick
from kbo.league.fa import run_fa_market, seed_service_years
from kbo.league.season import SeasonRunner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-fa", action="store_true")
    args = ap.parse_args()
    use_fa = not args.no_fa

    teams = load_league()
    init_market(teams)
    seed_service_years(teams)
    rng = random.Random(args.seed)

    rank_hist = defaultdict(list)
    champs = Counter()
    ps_appear = Counter()          # top5 = KBO 포스트시즌 진출
    fa_in = Counter()              # 팀별 외부 FA 영입 수
    fa_spend = Counter()           # 팀별 FA 지출 (AAV+보상)
    grade_decl, grade_move = Counter(), Counter()
    narratives = []                # FM 서사 샘플
    overpays = []                  # (aav/fair) 경쟁 오퍼 2+ 이적만

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

        offseason_tick(rng, teams, year=s, draft_mode=True)
        if use_fa:
            rep = run_fa_market(rng, teams, st, year=s)
            for sg in rep.signings:
                grade_decl[sg.grade] += 1
            for m in rep.moved:
                grade_move[m.grade] += 1
                fa_in[m.to_tid] += 1
                fa_spend[m.to_tid] += m.aav + m.comp
                if m.n_offers >= 2:
                    overpays.append(m.aav / m.fair)
                to_rank, from_rank = rank[m.to_tid], rank[m.from_tid]
                # 서사: 노장이 우승권(top3)으로 / 젊은 FA가 하위권(7+)으로
                if m.player.age >= 34 and to_rank <= 3 and len(narratives) < 6:
                    narratives.append(f"노장 {m.player.name}({m.player.age}세 "
                                      f"{m.grade}) {m.from_tid}({from_rank}위)→"
                                      f"{m.to_tid}({to_rank}위, 우승권) "
                                      f"AAV {m.aav} (적정 {m.fair})")
                if m.player.age <= 29 and to_rank >= 7 and len(narratives) < 6:
                    narratives.append(f"젊은 {m.player.name}({m.player.age}세 "
                                      f"{m.grade}) {m.from_tid}({from_rank}위)→"
                                      f"{m.to_tid}({to_rank}위, 출전기회) "
                                      f"AAV {m.aav}")
        run_draft(rng, teams, st, year=s)
        offseason_finance_tick(rng, teams, year=s)

    tag = "FA 포함" if use_fa else "FA 제외 (기준선)"
    print(f"=== FA 검증 [{tag}] ({args.seasons}시즌, seed={args.seed}) ===\n")
    print("[★ 순위 순환/편중] 팀별 우승·PS진출·순위 (독식/영구바닥 없어야)")
    print(f"  {'팀':<5}{'우승':>4}{'PS진출':>6}{'평균순위':>7}{'최고':>4}{'최저':>4}"
          + ("  FA영입  FA지출" if use_fa else ""))
    for t in sorted(teams, key=lambda t: -champs[t.tid]):
        r = rank_hist[t.tid]
        extra = (f"{fa_in[t.tid]:>6}{fa_spend[t.tid]:>8.0f}" if use_fa else "")
        print(f"  {t.tid:<5}{champs[t.tid]:>4}{ps_appear[t.tid]:>6}"
              f"{sum(r)/len(r):>7.1f}{min(r):>4}{max(r):>4}" + extra)
    mx = max(champs.values())
    zero = [t.tid for t in teams if champs[t.tid] == 0]
    print(f"  최다 우승 {mx}/{args.seasons} · 우승 0회 팀 {zero or '없음'}")

    if use_fa:
        total_mv = sum(grade_move.values())
        total_dc = sum(grade_decl.values())
        print(f"\n[시장 sanity] 자격 {total_dc}건 중 이적 {total_mv}건"
              f" ({total_mv/total_dc:.0%}) — 대다수 잔류")
        print("[등급 이동률] " + " · ".join(
            f"{g}: {grade_move[g]}/{grade_decl[g]}"
            f" ({grade_move[g]/grade_decl[g]:.0%})" if grade_decl[g] else f"{g}: -"
            for g in "ABC"))
        if overpays:
            print(f"[오버페이] 경쟁(2+ 오퍼) 이적 {len(overpays)}건, "
                  f"낙찰/적정 평균 {sum(overpays)/len(overpays):.2f}배 "
                  f"최대 {max(overpays):.2f}배")
        print("[FM 서사 샘플]")
        for n in narratives or ["(샘플 없음)"]:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
