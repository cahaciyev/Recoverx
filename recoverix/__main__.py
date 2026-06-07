"""Entry point: python -m recoverix"""
from __future__ import annotations

from .core.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    from .ui.app import run
    run()


if __name__ == "__main__":
    main()
