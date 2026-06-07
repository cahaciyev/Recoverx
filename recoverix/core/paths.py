"""Application data paths.

Keeps all writable state (database, logs, preferences) outside the program
directory so the app works whether it is run as a single .exe or from source.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    """Return the per-user writable data directory, creating it if needed."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        root = Path(base) / "Recoverix"
    else:
        root = Path.home() / ".recoverix"
    root.mkdir(parents=True, exist_ok=True)
    return root


def logs_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def database_path() -> Path:
    return app_data_dir() / "recoverix.db"


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource path (works under PyInstaller --onefile)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative
