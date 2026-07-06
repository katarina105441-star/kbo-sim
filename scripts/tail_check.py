"""분포 꼬리 검증 — N시즌 리그 리더(타이틀 홀더)의 값 분포를 확인.

리그 평균이 맞아도 극단값(리더)이 좁게 뭉치면 시뮬 분산이 부족한 것.
사용법:  python scripts/tail_check.py [--seasons 20] [--seed 11]
"""
import argparse
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.season import SeasonRunner

Q_PA = 446   # 규정타석 144*3.1
Q_OUT = 432  # 규정이닝 144이닝 = 432아웃

# 실제 KBO 최근 5년(2020~2024) 타이틀 값 참고 범위
REAL = {
    "타율왕":   ".339 ~ .360",
    "홈런왕":   "31 ~ 47",
    "타점왕":   "101 ~ 135",
    "도루왕":   "35 ~ 64",
    "다승왕":   "15 ~ 20",
    "탈삼진왕": "182 ~ 225",
    "ERA 1위":  "2.00 ~ 2.53",
}


def season_leaders(teams):
    bats = [p for t in teams for p in t.roster if p.season_bat.pa > 0]
    pits = [p for t in teams for p in t.roster if p.season_pit.outs > 0]
    # 규정타석/규정이닝 충족자만 비율 타이틀 대상 (부상 결장으로 미달 시 제외)
    qb = [p for p in bats if p.season_bat.pa >= Q_PA]
    qp = [p for p in pits if p.season_pit.outs >= Q_OUT]
    if not qb:  # 안전장치: 전원 미달이면 타석 상위 30명
        qb = sorted(bats, key=lambda p: p.season_bat.pa, reverse=True)[:30]
    if not qp:
        qp = sorted(pits, key=lambda p: p.season_pit.outs, reverse=True)[:15]
    out = {}
    p = max(qb, key=lambda x: x.season_bat.avg); out["타율왕"] = (p.season_bat.avg, p.name)
    p = max(bats, key=lambda x: x.season_bat.hr); out["홈런왕"] = (p.season_bat.hr, p.name)
    p = max(bats, key=lambda x: x.season_bat.rbi); out["타점왕"] = (p.season_bat.rbi, p.name)
    p = max(bats, key=lambda x: x.season_bat.sb); out["도루왕"] = (p.season_bat.sb, p.name)
    p = max(pits, key=lambda x: x.season_pit.w); out["다승왕"] = (p.season_pit.w, p.name)
    p = max(pits, key=lambda x: x.season_pit.so); out["탈삼진왕"] = (p.season_pit.so, p.name)
    p = min(qp, key=lambda x: x.season_pit.era); out["ERA 1위"] = (p.season_pit.era, p.name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=20)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    teams = load_league()
    rng = random.Random(args.seed)
    series: dict[str, list] = {k: [] for k in REAL}
    names: dict[str, Counter] = {k: Counter() for k in REAL}
    missed_reg, n_qb, n_qp = [], [], []

    for s in range(args.seasons):
        season = SeasonRunner(teams, rng)
        season.run()
        for k, (v, name) in season_leaders(teams).items():
            series[k].append(v)
            names[k][name] += 1
        regs = [p for t in teams for p in t.roster
                if not p.is_pitcher and p.season_bat.pa >= 250]
        missed_reg.append(sum(p.missed for p in regs) / len(regs) if regs else 0)
        n_qb.append(sum(1 for t in teams for p in t.roster
                        if not p.is_pitcher and p.season_bat.pa >= Q_PA))
        n_qp.append(sum(1 for t in teams for p in t.roster
                        if p.is_pitcher and p.season_pit.outs >= Q_OUT))

    print(f"=== 리그 리더 분포 ({args.seasons}시즌, seed={args.seed}) ===\n")
    print(f"{'부문':<8}{'최소':>8}{'평균':>8}{'최대':>8}   {'실제 KBO(20~24)':<16} 최다 수상자")
    for k in REAL:
        vs = series[k]
        lo, hi, mean = min(vs), max(vs), sum(vs) / len(vs)
        fmt = (lambda v: f"{v:.3f}") if k in ("타율왕", "ERA 1위") else (lambda v: f"{v:.0f}")
        top3 = ", ".join(f"{n}×{c}" for n, c in names[k].most_common(3))
        print(f"{k:<9}{fmt(lo):>8}{fmt(mean):>8}{fmt(hi):>8}   {REAL[k]:<18}{top3}")

    avg_missed = sum(missed_reg) / len(missed_reg)
    print(f"\n(부상) 주전 야수(250PA+) 평균 결장 {avg_missed:.1f}경기 ({avg_missed / 144:.1%})"
          f" · 규정타석 충족 {sum(n_qb) / len(n_qb):.0f}명 · 규정이닝 충족 {sum(n_qp) / len(n_qp):.1f}명")


if __name__ == "__main__":
    main()
