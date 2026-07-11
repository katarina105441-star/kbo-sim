"""KBO 매니저 로컬 실행기.

사용법:
    python run_game.py
    python run_game.py --port 8001 --no-browser
"""
from __future__ import annotations

import argparse
import os
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_PORT = 8010
ROOT = Path(__file__).resolve().parent


def port_available(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_port(preferred: int = DEFAULT_PORT) -> int:
    for port in range(preferred, MAX_PORT + 1):
        if port_available(port):
            return port
    raise RuntimeError(
        f"사용 가능한 포트가 없습니다. {preferred}~{MAX_PORT} 포트를 확인하세요."
    )


def wait_for_server(url: str, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    health_url = f"{url}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def open_browser_when_ready(url: str) -> None:
    if wait_for_server(url):
        webbrowser.open(url)
    else:
        print(f"브라우저 자동 실행에 실패했습니다. 직접 접속하세요: {url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KBO 매니저 실행")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--host", default=HOST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(ROOT)
    port = args.port if port_available(args.port, args.host) else choose_port(args.port)
    url = f"http://{args.host}:{port}"

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "필수 패키지가 없습니다. 먼저 'python -m pip install -r requirements.txt'를 실행하세요."
        ) from exc

    print("=" * 58)
    print(" KBO 매니저")
    print(f" 접속 주소: {url}")
    print(" 종료: 이 창에서 Ctrl+C")
    print("=" * 58)

    if not args.no_browser:
        threading.Thread(
            target=open_browser_when_ready, args=(url,), daemon=True
        ).start()

    uvicorn.run(
        "web.backend.main:app",
        host=args.host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
