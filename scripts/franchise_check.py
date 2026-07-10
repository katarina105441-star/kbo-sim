"""프랜차이즈 검증 — N시즌 연속 시뮬 + 오프시즌 에이징 (DESIGN_AGING.md §5).

최우선: 리그 지표(타율/ERA/득점)가 시즌이 지나도 드리프트 없이 횡보하는가.
드리프트 시 은퇴자 OVR 총량 vs 신인 OVR 총량으로 원인 분리 진단.
사용법: python scripts/franchise_check.py [--seasons 12] [--seed 7]
"""
import argparse
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kbo.io.loader import load_league
from kbo.league.aging import offseason_tick, overall, potential
from kbo.league.season import SeasonRunner

SAMPLES = ["김도영", "최형우", "문동주"]  # 젊은 야수 / 베테랑 야수 / 젊은 투수


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    teams = load_league()
    rng = random.Random(args.seed)
    rows = []                      # 시즌별 리그 지표
    age_ovr = defaultdict(list)    # 나이 → OVR (시즌 시작 시점, 전 시즌 누적)
    old_elite = 0                  # 38세+ OVR 80+ (선수-시즌)
    young_crash = 0                # 26세 이하 연간 OVR -4 이상
    total_players = 0
    traj = defaultdict(list)       # 샘플 궤적
    sample_pids = {p.pid: p.name for t in teams for p in t.roster if p.name in SAMPLES}

    for s in range(1, args.seasons + 1):
        for t in teams:
            for p in t.roster:
                age_ovr[p.age].append(overall(p))
                if p.age >= 38 and overall(p) >= 80:
                    old_elite += 1
                if p.pid in sample_pids:
                    pot = f"(pot {potential(p):.0f})" if p.tal_g and p.age < 30 else ""
                    traj[p.name].append(f"{p.age}세 {overall(p):.1f}{pot}")
        total_players += sum(len(t.roster) for t in teams)

        season = SeasonRunner(teams, rng)
        season.run()
        tot = season.league_totals()
        rows.append((s, tot.bat.avg, tot.bat.obp, tot.bat.slg, tot.pit.era,
                     tot.r_per_game, tot.hr_per_game))

        before = {p.pid: overall(p) for t in teams for p in t.roster}
        rep = offseason_tick(rng, teams, year=s)
        for t in teams:
            for p in t.roster:
                if p.pid in before and p.age <= 26 and before[p.pid] - overall(p) >= 4:
                    young_crash += 1
        ret_ovr = [overall(p) for _, p in rep.retired]
        rook_ovr = [overall(p) for _, p in rep.rookies]
        rows[-1] += (len(ret_ovr),
                     sum(ret_ovr) / len(ret_ovr) if ret_ovr else 0.0,
                     sum(rook_ovr) / len(rook_ovr) if rook_ovr else 0.0)

    print(f"=== 프랜차이즈 검증 ({args.seasons}시즌, seed={args.seed}) ===\n")
    print("시즌   타율   출루   장타   ERA   득점/G  HR/G   은퇴  은퇴OVR 신인OVR")
    for (s, avg, obp, slg, era, rg, hg, n_ret, r_ovr, k_ovr) in rows:
        print(f"{s:>3}  {avg:.3f}  {obp:.3f}  {slg:.3f}  {era:5.2f}  {rg:5.2f}"
              f"  {hg:5.2f}   {n_ret:>3}  {r_ovr:6.1f}  {k_ovr:6.1f}")
    f, l = rows[0], rows[-1]
    print(f"\n드리프트(첫→막): 타율 {l[1] - f[1]:+.3f} / ERA {l[4] - f[4]:+.2f}"
          f" / 득점 {l[5] - f[5]:+.2f}"
          f"  → {'횡보 OK' if abs(l[1] - f[1]) <= .010 and abs(l[4] - f[4]) <= .40 else '드리프트 의심'}")

    print("\n나이별 평균 OVR (전 시즌 누적, 산 모양 + 30대 중반 하락 확인):")
    for age in sorted(age_ovr):
        vs = age_ovr[age]
        bar = "#" * int((sum(vs) / len(vs) - 40) / 1.5)
        print(f"  {age:>2}세 ({len(vs):>4}명) {sum(vs) / len(vs):5.1f} {bar}")

    print(f"\n극단 사례: 38세+ OVR80+ {old_elite}건 / 26세 이하 급노쇠(-4/년) "
          f"{young_crash}건  (선수-시즌 {total_players}건 중)")

    print("\n샘플 궤적:")
    for name in SAMPLES:
        steps = traj.get(name, [])
        print(f"  {name}: " + " → ".join(steps) + ("" if len(steps) == args.seasons else "  [은퇴]"))


if __name__ == "__main__":
    main()
