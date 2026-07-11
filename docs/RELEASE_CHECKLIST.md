# 릴리스 체크리스트

릴리스 전에 아래 항목을 순서대로 확인합니다.

## 1. 기본 검증

```bash
python -m unittest discover -s tests
python -c "import web.backend.main; print('FastAPI import OK')"
```

## 2. 프론트엔드 빌드

```bash
cd web/frontend
npm ci
npm run build
```

빌드 결과는 `web/frontend/dist`에 생성됩니다. 이 저장소는 브라우저 실행용 정적 빌드본을 함께 커밋합니다.

## 3. 장기 밸런스 검증

릴리스 전 전체 검증은 아래 명령을 권장합니다.

```bash
python scripts/career_balance_check.py --seeds 4 --seasons 30 --strict
```

이 검증은 실제 정규시즌·포스트시즌·에이징·트레이드·FA·드래프트·재정 엔진을 사용합니다.

## 4. 자동 릴리스 점검

아래 명령은 문서, 주요 파일, Python 테스트, FastAPI import를 한 번에 점검합니다.

```bash
python scripts/release_check.py
```

프론트엔드 빌드는 Node 환경이 있는 경우 아래처럼 포함할 수 있습니다.

```bash
python scripts/release_check.py --frontend
```

장기 검증까지 포함하려면 아래처럼 실행합니다.

```bash
python scripts/release_check.py --frontend --balance
```

## 5. 수동 스모크 테스트

브라우저에서 아래 흐름을 직접 확인합니다.

1. `python -m uvicorn web.backend.main:app --port 8000`
2. `http://localhost:8000` 접속
3. 첫 화면의 3분 시작 가이드 표시 확인
4. 팀 선택 후 새 게임 시작
5. 하루 진행
6. 직접 운영 시작 후 1타석 진행
7. 라인업 탭 진입
8. 오프시즌 또는 시즌 끝까지 진행 시 이벤트/오프시즌 차단 안내 확인
9. 저장 후 서버 재시작
10. 저장된 게임 불러오기

## 6. 릴리스 노트 작성 기준

릴리스 노트에는 다음을 포함합니다.

- 주요 신규 기능
- 저장 파일 호환 여부
- 검증 결과
- 알려진 이슈
- 첫 실행 방법

현재 릴리스 노트 초안은 `docs/RELEASE_NOTES_MVP3.md`입니다.
