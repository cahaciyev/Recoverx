"""Recoverix launcher (used as the PyInstaller entry point)."""
from __future__ import annotations

import multiprocessing

from recoverix.core.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    from recoverix.ui.app import run
    run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
