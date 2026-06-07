"""Build a single-file Recoverix.exe with PyInstaller.

Usage:
    python -m pip install -r requirements.txt
    python build.py

Produces:  dist/Recoverix.exe
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Run: pip install -r requirements.txt")
        return 1

    # clean previous artefacts
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)

    sep = ";" if sys.platform.startswith("win") else ":"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", "Recoverix",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--uac-admin",                       # request elevation for physical disk access
        "--collect-all", "customtkinter",    # bundle CTk assets
        "--add-data", f"{ROOT / 'recoverix' / 'resources'}{sep}recoverix/resources",
        "--hidden-import", "PIL._tkinter_finder",
        str(ROOT / "main.py"),
    ]
    icon = ROOT / "recoverix" / "resources" / "icon.ico"
    if icon.exists():
        args[args.index("--onefile"):args.index("--onefile")] = ["--icon", str(icon)]

    print("Running:", " ".join(args))
    result = subprocess.run(args)
    if result.returncode == 0:
        exe = ROOT / "dist" / ("Recoverix.exe" if sys.platform.startswith("win") else "Recoverix")
        print("\nBuild complete ->", exe)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
