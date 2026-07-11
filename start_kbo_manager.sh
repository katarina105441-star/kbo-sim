#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3를 찾을 수 없습니다. https://www.python.org/downloads/ 에서 설치하세요."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] 전용 실행 환경을 만드는 중..."
  "$PYTHON_BIN" -m venv .venv
fi

if [ ! -f ".venv/.kbo-ready-0.5.0" ]; then
  echo "[2/3] 필수 구성요소를 설치하는 중... 최초 1회만 실행됩니다."
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/.kbo-ready-0.5.0
else
  echo "[2/3] 설치 확인 완료"
fi

echo "[3/3] 게임을 시작합니다. 브라우저가 자동으로 열립니다."
exec .venv/bin/python run_game.py
