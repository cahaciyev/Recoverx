"""Structured local logging for Recoverix.

Logs are written only to the local app-data folder. Nothing leaves the machine.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the root 'recoverix' logger once and return it."""
    global _CONFIGURED
    logger = logging.getLogger("recoverix")
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    log_file = logs_dir() / "recoverix.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True
    logger.info("Logging initialised -> %s", log_file)
    return logger


def get_logger(name: str = "recoverix") -> logging.Logger:
    return logging.getLogger(name if name.startswith("recoverix") else f"recoverix.{name}")
