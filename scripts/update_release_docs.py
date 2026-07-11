"""README의 사용자 실행 안내와 완료 상태를 현재 릴리스에 맞춘다."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PREFIX = """# KBO 매니저

KBO 구단 하나를 맡아 경기 운영, 선수단 관리, 트레이드·FA·드래프트,
구단주 평가, 해임·재취업, 은퇴와 명예의 전당까지 진행하는 장기 야구 시뮬레이션입니다.

- 현재 버전: **0.5.0 — MVP-3 Complete**
- 요구 환경: Python 3.10 이상
- 프론트엔드 빌드본 포함: 일반 사용자는 Node.js 설치 불필요
- 게임 엔진: 표준 라이브러리 기반, 동일 시드 재현 가능
- 빠른 안내: [QUICKSTART.md](QUICKSTART.md)
- 설계 문서: [DESIGN.md](DESIGN.md) · 능력치 산정: [data/RATINGS_METHOD.md](data/RATINGS_METHOD.md)

## 가장 쉬운 실행

### Windows

릴리스 ZIP을 압축 해제한 뒤 **`게임 시작.bat`**를 더블클릭합니다.
최초 1회 전용 가상환경과 필수 구성요소를 자동 설치하고 브라우저를 엽니다.

### macOS·Linux

```bash
chmod +x start_kbo_manager.sh
./start_kbo_manager.sh
```

### 직접 실행

```bash
python -m pip install -r requirements.txt
python run_game.py
```

기본 접속 주소는 `http://127.0.0.1:8000`입니다. 8000번 포트가 사용 중이면
실행기가 8010번까지 빈 포트를 자동 선택합니다.

## 첫 커리어 흐름

1. 고유 운영 철학을 가진 10개 구단 중 하나를 선택합니다.
2. 대시보드에서 시즌 목표와 구단주 신뢰도를 확인합니다.
3. 하루·시리즈·한 달·시즌 끝까지 진행하거나 내 팀 경기를 직접 운영합니다.
4. 라인업·1군/2군·육성 방향을 관리합니다.
5. 오프시즌에 트레이드·FA·보상선수·드래프트에 직접 개입합니다.
6. 성적에 따라 평가·해임·재취업·구단 이동이 발생합니다.
7. 10시즌 이후 은퇴할 수 있으며 30시즌에는 자동으로 최종 결산합니다.

첫 실행 안내와 상단 **도움말** 버튼에서 조작 방법을 다시 볼 수 있습니다.
저장 파일은 `saves/save.pkl`에 생성됩니다.

## 주요 기능

- 144경기 정규시즌과 KBO 계단식 포스트시즌
- 실시간 경기 운영: 투수 교체·대타·대주자·대수비
- 라인업·수비 위치·선발 로테이션·불펜 보직 편집
- 1군·2군 이동과 유망주 육성
- 직접 트레이드 협상, FA 입찰, 보상선수, 신인 드래프트
- 구단별 감독·스카우팅·운영 성향
- 시즌 목표·구단주 이벤트·신뢰도·업적
- 실제 해임·재취업·구단 이동·팬 및 미디어 반응
- 감독 은퇴·레거시 점수·명예의 전당·커리어 결산
- 기존 저장 파일 자동 마이그레이션

## 배포 패키지 생성

```bash
python scripts/build_release.py --output release
```

`KBO-Manager-0.5.0.zip`과 `KBO-Manager-0.5.0.tar.gz`가 생성됩니다.
`v*` 태그를 푸시하면 GitHub Actions가 테스트·프론트 빌드·패키징을 수행하고
GitHub Release에 결과물을 게시합니다.
"""


def update_readme(path: Path | None = None) -> Path:
    path = path or ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    marker = "## 콘솔 실행"
    if marker not in text:
        raise ValueError("README console marker not found")
    suffix = text[text.index(marker):]
    text = PREFIX.rstrip() + "\n\n" + suffix
    text = text.replace(
        "다음 확장: 사용자 경험 정리, 첫 실행 안내, 배포·릴리스 패키징.",
        "5단계 사용자 경험·릴리스 완료: 첫 실행 안내·오류 복구·원클릭 런처·ZIP/TAR 패키징·태그 릴리스 자동화 ✔\n"
        "다음 확장: 실제 사용자 피드백 기반 UX 보정과 정식 버전 태그 발행.",
    )
    path.write_text(text, encoding="utf-8")
    return path


if __name__ == "__main__":
    print(update_readme())
