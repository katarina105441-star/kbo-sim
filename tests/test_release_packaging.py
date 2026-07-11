"""첫 실행 런처와 배포 패키지 검증."""
from __future__ import annotations

import socket
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from kbo.version import RELEASE_NAME, __version__
from run_game import choose_port, port_available
from scripts.build_release import PACKAGE_NAME, build_release


class TestLauncherAndRelease(unittest.TestCase):
    def test_version_metadata_is_release_ready(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")
        self.assertTrue(RELEASE_NAME)
        self.assertEqual(PACKAGE_NAME, f"KBO-Manager-{__version__}")

    def test_choose_port_skips_busy_port(self):
        busy_port = next(
            (port for port in range(8000, 8010)
             if port_available(port) and port_available(port + 1)),
            None,
        )
        if busy_port is None:
            self.skipTest("연속으로 비어 있는 테스트 포트가 없습니다.")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", busy_port))
            self.assertFalse(port_available(busy_port))
            chosen = choose_port(busy_port)
            self.assertEqual(chosen, busy_port + 1)
            self.assertTrue(port_available(chosen))

    def test_release_builder_creates_both_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            zip_path, tar_path = build_release(Path(temp))
            self.assertTrue(zip_path.is_file())
            self.assertTrue(tar_path.is_file())
            self.assertGreater(zip_path.stat().st_size, 0)
            self.assertGreater(tar_path.stat().st_size, 0)

    def test_release_zip_contains_runtime_files_and_excludes_sources_not_needed(self):
        with tempfile.TemporaryDirectory() as temp:
            zip_path, _ = build_release(Path(temp))
            root = f"{PACKAGE_NAME}/"
            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
            required = {
                root + "게임 시작.bat",
                root + "start_kbo_manager.sh",
                root + "run_game.py",
                root + "requirements.txt",
                root + "QUICKSTART.md",
                root + "web/backend/main.py",
                root + "web/frontend/dist/index.html",
                root + "kbo/version.py",
            }
            self.assertFalse(required - names)
            self.assertFalse(any("node_modules" in name for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith(".pyc") for name in names))

    def test_release_tar_has_executable_shell_launcher(self):
        with tempfile.TemporaryDirectory() as temp:
            _, tar_path = build_release(Path(temp))
            member_name = f"{PACKAGE_NAME}/start_kbo_manager.sh"
            with tarfile.open(tar_path) as archive:
                member = archive.getmember(member_name)
            self.assertTrue(member.mode & 0o100)


if __name__ == "__main__":
    unittest.main()
