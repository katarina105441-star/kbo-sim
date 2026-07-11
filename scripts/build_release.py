"""배포용 ZIP/TAR.GZ 패키지를 재현 가능하게 생성한다."""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

from kbo.version import __version__

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = f"KBO-Manager-{__version__}"

INCLUDE_PATHS = (
    "kbo",
    "data",
    "web/backend",
    "web/frontend/dist",
    "requirements.txt",
    "run_game.py",
    "게임 시작.bat",
    "start_kbo_manager.sh",
    "README.md",
    "QUICKSTART.md",
)

EXCLUDED_NAMES = {
    ".git", ".github", ".venv", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", "saves", "release", "dist-release",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}


def should_include(path: Path) -> bool:
    if any(part in EXCLUDED_NAMES for part in path.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def copy_entry(source: Path, destination: Path) -> None:
    if source.is_dir():
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            if not should_include(relative):
                continue
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def stage_release(stage_root: Path) -> Path:
    package_root = stage_root / PACKAGE_NAME
    package_root.mkdir(parents=True, exist_ok=True)
    for relative in INCLUDE_PATHS:
        source = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"릴리스 필수 파일이 없습니다: {relative}")
        copy_entry(source, package_root / relative)
    (package_root / "saves").mkdir(exist_ok=True)
    shell_script = package_root / "start_kbo_manager.sh"
    shell_script.chmod(shell_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return package_root


def write_zip(package_root: Path, output_dir: Path) -> Path:
    output = output_dir / f"{PACKAGE_NAME}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package_root.parent))
    return output


def write_tar(package_root: Path, output_dir: Path) -> Path:
    output = output_dir / f"{PACKAGE_NAME}.tar.gz"
    with tarfile.open(output, "w:gz") as archive:
        archive.add(package_root, arcname=package_root.name)
    return output


def build_release(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kbo-release-") as temp:
        package_root = stage_release(Path(temp))
        return write_zip(package_root, output_dir), write_tar(package_root, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KBO 매니저 릴리스 패키지 생성")
    parser.add_argument("--output", default="release", help="출력 폴더")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    zip_path, tar_path = build_release((ROOT / args.output).resolve())
    print(f"ZIP: {zip_path}")
    print(f"TAR.GZ: {tar_path}")


if __name__ == "__main__":
    main()
