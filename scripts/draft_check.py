"""신인 드래프트 검증 — 30시즌 완전판 (DESIGN_DRAFT.md §7).

★ 최우선: 순위 순환 (돈+역순지명 두 축). 특정 구단 영구지배/영구바닥 없이
순환하는지. + 역순효과·Need/BPA·스카우팅 불확실성·회귀.
오프시즌 체인: season → 에이징(은퇴,draft_mode) → 드래프트(refill) → 재정.
"""
import argparse
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick, overall
from kbo.league.draft import need_bonus, run_draft
from kbo.league.economy import init_market, offseason_finance_tick
from kbo.league.season import SeasonRunner


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    vy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return cov / (vx * vy) if vx and vy else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    teams = load_league()
    init_market(teams)
    rng = random.Random(args.seed)

    rank_hist = defaultdict(list)          # tid -> [순위/시즌]
    val_by_rank = defaultdict(list)        # 지명팀 전시즌순위 -> [지명 true_val]
    from kbo.engine.probability import TUNE
    _ms, _ls = TUNE["draft"]["round_mid_start"], TUNE["draft"]["round_late_start"]
    B_HI = f"상위(1~{_ms-1}R)" if _ms > 2 else "상위(1R)"
    B_MID = f"중위({_ms}~{_ls-1}R)"
    B_LO = f"하위({_ls}R~)"

    need_fill, bpa_cases = 0, 0
    n_picks = 0
    band_picks = {B_HI: [0, 0], B_MID: [0, 0], B_LO: [0, 0]}   # [약점픽, 총]
    band_age = {B_HI: [], B_MID: [], B_LO: []}                  # 실링(젊음) 확인
    bpa_samples = []                       # 상위R 특급 Need무시 샘플
    order_val = []                         # (overall_pick_idx, true_val) 스카우팅용
    bust_steal = []                        # 샘플 (라운드, scouted, true)
    rebound_samples = []

    prev_rank = None
    for s in range(1, args.seasons + 1):
        season = SeasonRunner(teams, rng)
        season.run()
        standings = season.standings()
        rank = {t.tid: i for i, t in enumerate(standings, 1)}
        for t in teams:
            rank_hist[t.tid].append(rank[t.tid])
        # 반등 샘플: 전 시즌 9~10위가 올 시즌 top-3
        if prev_rank:
            for t in teams:
                if prev_rank.get(t.tid, 5) >= 9 and rank[t.tid] <= 3:
                    rebound_samples.append((t.tid, prev_rank[t.tid], rank[t.tid], s))
        prev_rank = rank

        offseason_tick(rng, teams, year=s, draft_mode=True)
        picks = run_draft(rng, teams, standings, year=s)
        offseason_finance_tick(rng, teams, year=s)

        for idx, pk in enumerate(picks):
            n_picks += 1
            val_by_rank[rank[pk.tid]].append(pk.true_val)
            order_val.append((idx, pk.true_val))
            weak = pk.need > 0.5                     # 약점 포지션 지명 여부(원 Need)
            if weak:
                need_fill += 1
            band = (B_HI if pk.round < _ms else B_MID if pk.round < _ls else B_LO)
            band_picks[band][1] += 1
            band_age[band].append(pk.player.age)
            if weak:
                band_picks[band][0] += 1
            if pk.need < 0.5 and pk.scouted > 22:    # 니드 낮은데 뽑은 고가치 = BPA
                bpa_cases += 1
                if pk.round < _ms and len(bpa_samples) < 3:
                    bpa_samples.append((pk.tid, pk.round, pk.player.pos,
                                        round(pk.scouted, 1)))
            if pk.round <= 2 and pk.true_val < 8:    # 상위픽 bust
                bust_steal.append(("bust", pk.round, pk.scouted, pk.true_val))
            elif pk.round >= 6 and pk.true_val > 22:  # 늦뽑 대박
                bust_steal.append(("steal", pk.round, pk.scouted, pk.true_val))

    print(f"=== 드래프트 검증 ({args.seasons}시즌, seed={args.seed}) ===\n")

    print("[★ 순위 순환] 구단별 순위 분포 (영구지배/영구바닥 없어야)")
    print(f"  {'팀':<5}{'최고':>4}{'평균':>6}{'최저':>4}{'top3':>6}{'bot3':>6}")
    for t in sorted(teams, key=lambda t: sum(rank_hist[t.tid]) / len(rank_hist[t.tid])):
        r = rank_hist[t.tid]
        top3 = sum(1 for x in r if x <= 3)
        bot3 = sum(1 for x in r if x >= 8)
        print(f"  {t.tid:<5}{min(r):>4}{sum(r)/len(r):>6.1f}{max(r):>4}{top3:>6}{bot3:>6}")
    stuck_top = [t.tid for t in teams if max(rank_hist[t.tid]) <= 4]
    stuck_bot = [t.tid for t in teams if min(rank_hist[t.tid]) >= 7]
    print(f"  영구 상위권(항상 4위 내): {stuck_top or '없음'} · "
          f"영구 하위권(항상 7위 밖): {stuck_bot or '없음'}")
    print(f"  꼴찌권(9~10위)→top3 반등 사례: {len(rebound_samples)}회"
          + (f" 예) {rebound_samples[0][0]} {rebound_samples[0][1]}위→{rebound_samples[0][2]}위"
             if rebound_samples else ""))

    print("\n[역순 효과] 지명팀 전시즌 순위별 지명 유망주 평균가치 (약팀↑ 이어야)")
    def band(lo, hi):
        vs = [v for r in range(lo, hi + 1) for v in val_by_rank[r]]
        return sum(vs) / len(vs) if vs else 0.0
    print(f"  꼴찌권(8~10위) {band(8,10):.1f} vs 상위권(1~3위) {band(1,3):.1f}"
          f"  (차이 {band(8,10)-band(1,3):+.1f})")

    print("\n[Need/BPA] 라운드 구간별 약점포지션 지명률 (상위 낮음 / 중위 높음 / 하위 낮음+젊음)")
    for band, (w, tot) in band_picks.items():
        age = band_age[band]
        avg_age = f" · 평균나이 {sum(age)/len(age):.1f}" if age else ""
        print(f"  {band:<11} 약점포지션 {w}/{tot} ({w/tot:.0%}){avg_age}"
              if tot else f"  {band:<11} -")
    print(f"  전체 약점포지션 지명 {need_fill}/{n_picks} ({need_fill/n_picks:.0%})"
          f" · BPA 예외(니드낮은 고가치) {bpa_cases}회")
    if bpa_samples:
        print(f"  BPA 샘플(상위R 특급 Need무시): "
              + ", ".join(f"{tid} {r}R {pos} 가치{v}" for tid, r, pos, v in bpa_samples))

    print("\n[스카우팅 불확실성] 지명순서 ↔ 실제가치")
    idxs = [i for i, _ in order_val]
    vals = [v for _, v in order_val]
    r = pearson(idxs, vals)
    busts = sum(1 for k, *_ in bust_steal if k == "bust")
    steals = sum(1 for k, *_ in bust_steal if k == "steal")
    print(f"  지명순서-실제가치 상관 r={r:.2f} (음의 상관이되 |r|<1 = 불완전 예측)")
    print(f"  상위픽 bust {busts}회 · 늦뽑 대박 {steals}회 (역전 존재)")


if __name__ == "__main__":
    main()
