# KBO 매니저 — 1단계: 데이터 모델 + 경기 시뮬레이션 엔진

Python 3.10+ / 표준 라이브러리만 사용. 설계 문서: [DESIGN.md](DESIGN.md) ·
능력치 산정 근거: [data/RATINGS_METHOD.md](data/RATINGS_METHOD.md)

## 실행

```bash
# 단일 경기 (박스스코어)          팀 ID: KIA LG DSN SSG SAM KT LTE HWE NC KWM
python scripts/play_game.py --home KIA --away LG --seed 42
python scripts/play_game.py --home HWE --away KWM --verbose   # 타석별 로그 포함

# 풀시즌 파이프라인 — 정규 144경기 → 순위 → 포스트시즌 → 우승팀 (+PS 개인기록)
python scripts/run_season.py --seed 2026

# 밸런싱 하네스 — N시즌 평균 지표 vs 실제 KBO 목표표
python scripts/calibrate.py --seasons 20 --seed 1

# 분포 검증 — 리그 리더 꼬리 / 포스트시즌 시드별 우승률·언더독 런
python scripts/tail_check.py --seasons 20
python scripts/ps_check.py --seasons 200

# 테스트
python -m unittest discover -s tests
```

## 구조

```
data/       실명 선수 250명(팀당 25) + 구단 메타. 능력치는 실제 성적 역산 (est=추정 표기)
kbo/models  Player / Team / 기록 (순수 데이터)
kbo/engine  probability(log5 수식+TUNE) → plate_appearance(타석 트리)
            → baserunning / defense / pitching_manager → game(경기 러너)
kbo/league  일정 + 시즌 러너 (불펜 연투 제한 포함)
kbo/io      로더 + 콘솔 리포트 (print는 여기서만)
scripts/    play_game / run_season / calibrate
```

- 엔진은 print 없음, `random.Random(seed)` 주입 → 같은 시드 = 같은 경기
- 모든 밸런싱 상수는 `kbo/engine/probability.py`의 `TUNE` 한 곳
- 파크팩터는 전 구장 1.0(중립) 뼈대만 — 값만 채우면 작동

## 캘리브레이션 상태 (2단계-3 등판간격/컨디션 도입 후, 50시즌 검증 완료)

리그 타율 .266 / 출루율 .343 / 장타율 .401 / ERA 4.70 (자책 기준, 비자책률 5%) /
득점 4.90 / 홈런 0.93/G / K/9 7.8 / BB/9 3.8 / 도루성공률 74% / 병살 116 / 실책 96
— **전 11지표 목표 범위 내.**
꼬리 분포(20시즌 × 시드 2): 타율왕 평균 .349~.352 · 홈런왕 35~37 · 타점왕 128 ·
도루왕 44~47 · 탈삼진왕 192~196 · ERA 1위 2.36~2.55 — 전 부문 실제 KBO 범위.
주전 야수 시즌 평균 결장 8.1% (부상) · 시즌 폼/핫콜드 스트릭 (컨디션) ·
선발 등판간격/불펜 연투 저하 (등판부하). 검증: `python scripts/tail_check.py`

## 포스트시즌 (계단식 토너먼트)

WC(4위 1승 어드밴티지) → 준PO(5전3선승) → PO(5전3선승) → KS(7전4선승, 홈 2-3-2).
단기전 지정 선발(에이스 중3일 재등판), 총력전 불펜, 시리즈 간 휴식,
장기 휴식 팀 경기감각 저하(rust), PS 개인 기록 분리 집계.
검증(350시즌): 1위 우승률 57.5~58.7% (실제 ~50-60%) · 5위 언더독 KS 진출 5.5~7.3% ·
중3일 선발 승률 열세·연투 불펜 22% 투입 확인.

## 다음 단계

**2단계 완료** (실책 ✔ 부상 ✔ 등판간격/컨디션 ✔ 포스트시즌 ✔)
이후 3단계: 구단 운영(FA/트레이드/성장) → 4단계: 웹 UI
