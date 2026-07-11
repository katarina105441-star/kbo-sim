"""릴리스 전 자동 점검 스크립트.

기본 실행은 빠른 검증만 수행한다.

    python scripts/release_check.py
    python scripts/release_check.py --frontend
    python scripts/release_check.py --frontend --balance
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "requirements.txt",
    "docs/FIRST_RUN.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/RELEASE_NOTES_MVP3.md",
    "web/frontend/src/onboarding.js",
    "web/frontend/dist/index.html",
]

REQUIRED_README_PHRASES = [
    "웹 UI 실행",
    "첫 실행",
    "감독 커리어",
]


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def check_files() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise SystemExit("필수 파일 누락: " + ", ".join(missing))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing_phrases = [phrase for phrase in REQUIRED_README_PHRASES
                       if phrase not in readme]
    if missing_phrases:
        raise SystemExit("README 핵심 문구 누락: " + ", ".join(missing_phrases))
    print("파일/문서 점검 OK")


def check_python() -> None:
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    run([sys.executable, "-c", "import web.backend.main; print('FastAPI import OK')"])


def check_frontend() -> None:
    run(["npm", "ci"], cwd=ROOT / "web" / "frontend")
    run(["npm", "run", "build"], cwd=ROOT / "web" / "frontend")


def check_balance() -> None:
    run([sys.executable, "scripts/career_balance_check.py", "--seeds", "4",
         "--seasons", "30", "--strict"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", action="store_true",
                        help="npm ci와 npm run build까지 실행")
    parser.add_argument("--balance", action="store_true",
                        help="4시드×30시즌 장기 커리어 검증까지 실행")
    args = parser.parse_args()

    check_files()
    check_python()
    if args.frontend:
        check_frontend()
    if args.balance:
        check_balance()
    print("\n릴리스 점검 PASS")


if __name__ == "__main__":
    main()
