"""연봉/계약·재정 검증 — 30시즌 연속 (DESIGN_CONTRACTS.md §7).

1 연봉 분포 리얼리즘  2 가치평가 sanity  3 런어웨이 방지  4 회귀(테스트)
5 시장차 고착 확인    6 장기 연봉 인플레

※ 한계: 드래프트 역순지명·FA·트레이드가 아직 없어 예산이 전력에 개입하지
   않는다. 따라서 3·5는 '돈 축'(예산 동역학이 유계·반응·비고착)만 검증하며,
   money→성적 연결은 드래프트 단계에서 재검증한다 (문서·출력 명시).
"""
import argparse
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.aging import ensure_talents, offseason_tick, overall
from kbo.league import contracts as C
from kbo.league.economy import (init_market, league_cap, offseason_finance_tick,
                                team_payroll)
from kbo.league.season import SeasonRunner

SAMPLES = ["김도영", "최형우", "문동주"]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def salary_snapshot(teams):
    return [p.contract.salary for t in teams for p in t.roster]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    teams = load_league()
    init_market(teams)
    rng = random.Random(args.seed)

    # 샘플 궤적은 첫 오프시즌(은퇴) 전 원본 로스터에서 잡는다 (최형우 43세 보존).
    ensure_talents(random.Random(args.seed), (p for t in teams for p in t.roster))
    cap0 = league_cap(1)
    byname = {p.name: (p, t) for t in teams for p in t.roster}
    sample_rows = []
    for nm in SAMPLES:
        if nm in byname:
            p, t = byname[nm]
            r = C.team_roles(t)[p.pid]
            sample_rows.append((nm, p.age, overall(p), C.war_now(p, r),
                                C.asset_war(p, r), C.fair_salary(p, cap0, r),
                                C.contract_value(p, cap0, r)))

    budget_hist = defaultdict(list)   # tid -> [budget/시즌]
    wins_hist = defaultdict(list)
    top_budget = defaultdict(int)     # tid -> top-3 예산 시즌 수
    tax_total = 0                     # 캡 초과(제재) 팀-시즌 수
    floor_total = 0                   # 하한 미달 팀-시즌 수
    sal_season1, sal_last = None, None

    for s in range(1, args.seasons + 1):
        season = SeasonRunner(teams, rng)
        season.run()
        offseason_tick(rng, teams, year=s)          # 에이징 (은퇴/신인)
        rep = offseason_finance_tick(rng, teams, year=s)   # 재정
        tax_total += len(rep.tax_payers)
        floor_total += len(rep.below_floor)

        for t in teams:
            budget_hist[t.tid].append(t.budget)
            wins_hist[t.tid].append(t.wins)
        for tm in sorted(teams, key=lambda t: t.budget, reverse=True)[:3]:
            top_budget[tm.tid] += 1

        if s == 1:
            sal_season1 = salary_snapshot(teams)
        if s == args.seasons:
            sal_last = salary_snapshot(teams)

    print(f"=== 재정 검증 ({args.seasons}시즌, seed={args.seed}) ===")
    print("※ money→성적 연결은 드래프트 단계 재검증 — 여기선 예산 동역학만 본다\n")

    print("[2] 가치평가 sanity (원본 로스터) — 젊은 특급=높은 asset, 노장=낮은 asset")
    print(f"  {'선수':<8}{'나이':>4}{'OVR':>5}{'war_now':>9}{'asset':>7}{'연봉(억)':>9}{'가치(억)':>9}")
    for nm, age, ov, wn, aw, sal, val in sample_rows:
        print(f"  {nm:<8}{age:>4}{ov:>5.0f}{wn:>9.1f}{aw:>7.1f}{sal:>9.1f}{val:>9.1f}")

    print("\n[1] 연봉 분포 (시즌30, 리그 전체) — 소수 고액 + 다수 저연봉 롱테일")
    s30 = sal_last
    print(f"  중앙값 {pct(s30,.5):.1f}억 · p90 {pct(s30,.9):.1f}억 · p99 {pct(s30,.99):.1f}억"
          f" · 최고 {max(s30):.1f}억 · 10억+ {sum(1 for x in s30 if x>=10)}명"
          f" · 최저({min(s30):.1f}) {sum(1 for x in s30 if x<=min(s30)+.01)}명")
    print(f"  경쟁균형세: 캡 초과(제재) {tax_total}팀-시즌 · 하한 미달 {floor_total}팀-시즌"
          f" / {args.seasons*10}  (소프트캡이 소수만 넘도록 유효)")

    print("\n[6] 장기 연봉 인플레 (시즌1 vs 시즌30) — 캡 +5%/yr 연동")
    s1 = sal_season1
    cap_growth = (league_cap(args.seasons) / league_cap(1) - 1) * 100
    print(f"  시즌1 : 중앙값 {pct(s1,.5):.1f} · p90 {pct(s1,.9):.1f} · 최고 {max(s1):.1f}억")
    print(f"  시즌30: 중앙값 {pct(s30,.5):.1f} · p90 {pct(s30,.9):.1f} · 최고 {max(s30):.1f}억")
    print(f"  캡 누적 상승 {cap_growth:.0f}% · 중앙연봉 상승 {(pct(s30,.5)/pct(s1,.5)-1)*100:.0f}%"
          f"  → {'현실적' if pct(s30,.5)/pct(s1,.5) <= league_cap(args.seasons)/league_cap(1)*1.2 else '과도(연동 완화 검토)'}")

    print("\n[3][5] 예산 동역학 — 유계·반응·비고착 / 시장차 고착 여부")
    print(f"  {'팀':<5}{'시장':>5}{'예산min':>8}{'예산avg':>8}{'예산max':>8}{'승avg':>6}{'예산top3':>8}")
    for t in sorted(teams, key=lambda t: t.market_size, reverse=True):
        b = budget_hist[t.tid]
        w = wins_hist[t.tid]
        print(f"  {t.tid:<5}{t.market_size:>5.2f}{min(b):>8.0f}{sum(b)/len(b):>8.0f}"
              f"{max(b):>8.0f}{sum(w)/len(w):>6.0f}{top_budget[t.tid]:>7}")
    # 고착 지표: 큰손(1.15)·짠물(0.90) 팀의 예산 top-3 점유
    big = sum(top_budget[t.tid] for t in teams if t.market_size >= 1.15)
    small = sum(top_budget[t.tid] for t in teams if t.market_size <= 0.90)
    frozen = [t.tid for t in teams if len(set(round(x, -1) for x in budget_hist[t.tid])) <= 2]
    print(f"  예산 top-3 점유: 큰손(3팀) {big}회 · 짠물(5팀) {small}회 (총 {args.seasons*3})")
    print(f"  → 짠물 팀도 top-3 진입({'있음 - 비고착 OK' if small > 0 else '없음 - 고착 의심'})"
          f" · 예산 사실상 고정팀 {frozen if frozen else '없음'}")


if __name__ == "__main__":
    main()
