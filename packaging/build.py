"""Build the self-contained desktop bundle: ``dist/circuits-llm-<platform>.zip``.

Steps: build the frontend into the Python package, run PyInstaller (one-folder
mode, with ngspice bundled on Windows) and zip the result.

Run with the backend venv's Python, which needs the ``package`` extra installed:

    backend/.venv/Scripts/python packaging/build.py      (Windows)
    backend/.venv/bin/python packaging/build.py          (macOS / Linux)
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
FRONTEND: Final = ROOT / "frontend"
BACKEND: Final = ROOT / "backend"
STATIC: Final = BACKEND / "src" / "circuits_llm" / "web" / "static"
NGSPICE_DIR: Final = ROOT / "vendor" / "ngspice" / "Spice64"
BUILD: Final = ROOT / "build"
DIST: Final = ROOT / "dist"
APP_NAME: Final = "circuits-llm"
_DATA_SEP: Final = ";" if sys.platform == "win32" else ":"


def _run(*command: str | Path, cwd: Path = ROOT) -> None:
    print("+", " ".join(str(part) for part in command))
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)  # noqa: S603


def _platform_tag() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64")
    return f"{system}-{machine}"


def build_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is required to build the frontend")
    _run(npm, "ci", cwd=FRONTEND)
    _run(npm, "run", "build:embed", cwd=FRONTEND)
    if not (STATIC / "index.html").is_file():
        raise SystemExit(f"frontend build did not produce {STATIC / 'index.html'}")


def build_bundle() -> Path:
    args: list[str | Path] = [
        sys.executable, "-m", "PyInstaller", ROOT / "packaging" / "entry.py",
        "--name", APP_NAME,
        "--onedir",
        "--noconfirm",
        "--clean",
        "--console",  # the console window shows the URL and lets users stop the server
        "--distpath", DIST,
        "--workpath", BUILD,
        "--specpath", BUILD,
        "--collect-data", "circuits_llm",
        "--collect-submodules", "uvicorn",
    ]  # fmt: skip
    if sys.platform == "win32":
        if not (NGSPICE_DIR / "bin" / "ngspice_con.exe").is_file():
            raise SystemExit(f"ngspice not found at {NGSPICE_DIR}; see README (Windows build)")
        args += ["--add-data", f"{NGSPICE_DIR}{_DATA_SEP}vendor/ngspice/Spice64"]
    _run(*args)
    return DIST / APP_NAME


def archive(bundle: Path) -> Path:
    target = DIST / f"{APP_NAME}-{_platform_tag()}"
    archive_path = shutil.make_archive(
        str(target), "zip", root_dir=bundle.parent, base_dir=bundle.name
    )
    return Path(archive_path)


def main() -> None:
    build_frontend()
    bundle = build_bundle()
    print(f"built {archive(bundle)}")


if __name__ == "__main__":
    main()
