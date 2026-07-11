# KBO 매니저 — MVP-3 감독 커리어 모드

KBO 매니지먼트 시뮬레이션입니다. 실제 선수 데이터 기반 능력치, 정규시즌·포스트시즌 엔진, 오프시즌 구단 운영, 감독 커리어를 하나의 웹 UI에서 진행합니다.

- Python 3.10+
- FastAPI 백엔드
- React 정적 프론트엔드 빌드본 포함
- 설계 문서: [DESIGN.md](DESIGN.md)
- 능력치 산정 근거: [data/RATINGS_METHOD.md](data/RATINGS_METHOD.md)
- 첫 실행 상세 안내: [docs/FIRST_RUN.md](docs/FIRST_RUN.md)
- 릴리스 체크리스트: [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md)
- MVP-3 릴리스 노트: [docs/RELEASE_NOTES_MVP3.md](docs/RELEASE_NOTES_MVP3.md)

## 바로 실행

최초 1회 설치:

```bash
python -m pip install -r requirements.txt
```

게임 실행:

```bash
python -m uvicorn web.backend.main:app --port 8000
```

브라우저에서 접속:

```text
http://localhost:8000
```

프론트엔드는 빌드본이 저장소에 포함되어 있어 일반 실행에는 Node 설치가 필요 없습니다. 화면을 수정하는 개발자만 `web/frontend`에서 `npm ci && npm run build`를 실행하면 됩니다.

## 3분 시작 순서

1. 첫 화면에서 운영할 구단을 선택합니다.
2. 시드는 비워도 됩니다. 같은 결과를 반복 검증할 때만 숫자를 넣습니다.
3. 대시보드에서 하루, 시리즈, 한 달, 시즌 끝까지 중 하나를 눌러 진행합니다.
4. 오늘 경기를 직접 지휘하려면 **직접 운영**을 누릅니다.
5. 구단주 이벤트, 트레이드, FA, 보상선수, 드래프트가 뜨면 먼저 처리해야 계속 진행됩니다.
6. 상단 **저장**을 자주 누르고, 다음 실행 때 **저장된 게임 불러오기**로 이어 합니다.

## 웹 UI 주요 기능

| 영역 | 기능 |
| --- | --- |
| 경기 진행 | 하루·시리즈·월·시즌 끝까지 진행, 오늘 경기 직접 운영 |
| 직접 운영 | 투수 교체, 대타, 대주자, 대수비, 타석 단위 진행 |
| 정보 확인 | 대시보드, 순위표, 일정·결과, 박스스코어, 로스터, 선수 상세 |
| 라인업 | 타순, 수비 슬롯, 선발 로테이션, 마무리, 셋업 직접 편집 |
| 육성 | 1군·2군 이동, 유망주 육성 방향 설정, 자동 콜업 |
| 오프시즌 | 트레이드, FA 입찰, FA 보상선수, 신인 드래프트 |
| 구단 개성 | 10개 구단별 운영 기조, 스카우팅 정확도, 선수 선호 반영 |
| 프런트 평가 | 시즌 목표, 구단주 신뢰도, 해임 위험, S~F 평가 |
| 커리어 | 실제 해임, 재취업, 구단 이동, 팬·언론 반응, 은퇴, 명예의 전당 |

## 진행이 멈추는 정상 상황

다음 메시지는 오류가 아니라 게임 규칙입니다.

- 구단주 이벤트에 먼저 응답해야 합니다.
- 트레이드/FA/보상선수/드래프트를 먼저 처리해야 합니다.
- 재취업할 구단을 먼저 선택해야 합니다.
- 은퇴한 감독의 커리어는 더 진행할 수 없습니다.

## 콘솔 실행

```bash
# 단일 경기, 팀 ID: KIA LG DSN SSG SAM KT LTE HWE NC KWM
python scripts/play_game.py --home KIA --away LG --seed 42
python scripts/play_game.py --home HWE --away KWM --verbose

# 풀시즌 파이프라인
python scripts/run_season.py --seed 2026

# 밸런싱 하네스
python scripts/calibrate.py --seasons 20 --seed 1
python scripts/tail_check.py --seasons 20
python scripts/ps_check.py --seasons 200
python scripts/franchise_check.py --seasons 12
python scripts/career_balance_check.py --seeds 4 --seasons 30 --strict

# 테스트
python -m unittest discover -s tests

# 릴리스 점검
python scripts/release_check.py
```

## 구조

```text
data/          실명 선수 250명과 구단 메타
kbo/models     Player, Team, 기록 데이터
kbo/engine     확률, 타석, 주루, 수비, 투수 운영, 경기 엔진
kbo/league     시즌, 포스트시즌, 에이징, 계약, FA, 트레이드, 드래프트, 커리어
kbo/io         로더와 콘솔 리포트
web/backend    FastAPI API와 세션 저장/복원
web/frontend   React UI와 정적 dist
scripts/       실행, 검증, 릴리스 점검 도구
docs/          첫 실행 안내, 릴리스 문서
```

## 검증 상태

- 단일 시즌 밸런스: 리그 타율, 출루율, 장타율, ERA, 득점, 홈런, K/9, BB/9, 도루성공률, 병살, 실책 목표 범위 내
- 포스트시즌: 1위 우승률, 5위 언더독 진출률, 중3일 선발/불펜 총력전 확인
- 에이징: 12시즌 드리프트, 나이별 OVR 산 모양, 신인 아키타입 기반 엘리트 재생산 확인
- FA: 이적률, 등급별 이동률, 오버페이, 순위 순환 유지 검증
- 트레이드: 거래 수, 등가비, 손해 거래 비중, 유망주 도박, 순위 순환 검증
- 감독 커리어: 4시드×30시즌 장기 검증에서 평균 해임 4.25회, 지휘 구단 4.75개, 우승 0.5회

## 알려진 이슈

1. 장기 모드에서 타율 +0.006~0.012, ERA +0.20~0.46 수준의 드리프트 경계가 남아 있습니다. 단일 시즌 밸런스는 테스트 가드 안에 있습니다.
2. TUNE 변경 시 RNG 스트림이 이동해 같은 시드도 다른 난수 우주가 됩니다. 장기 튜닝은 반드시 4시드 이상 하네스로 판단해야 합니다.
3. 브라우저 UI는 로컬 실행 기준입니다. 별도 호스팅 배포 자동화는 다음 단계입니다.

## MVP-3 완료 범위

- 라인업·수비 슬롯·선발 로테이션·마무리·셋업 직접 편집
- 실시간 경기 한 타석 진행과 수동 교체
- 1군·2군 이동과 유망주 육성
- 오프시즌 트레이드 직접 협상
- FA 직접 입찰
- FA 보상선수 보호명단과 지명/현금 선택
- 신인 드래프트 직접 지명
- 구단별 감독·스카우팅·운영 성향
- 시즌 목표·프런트 평가·구단주 신뢰도·해임 위험
- 구단주 이벤트·목표 보상·감독 업적
- 실제 해임·재취업·구단 이동·팬/언론 반응
- 자발 은퇴·자동 은퇴·레거시 등급·명예의 전당
- 첫 실행 안내·릴리스 문서·자동 릴리스 점검

## 다음 확장 후보

- 배포 자동화
- 여러 세이브 슬롯
- 초보자용 튜토리얼 오버레이
- 시즌 중 미디어/팬 이벤트 확장
- 실제 선수 데이터 업데이트 자동화
