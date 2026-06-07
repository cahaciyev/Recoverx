"""Local SQLite storage for scan sessions, recovered files and preferences.

Everything is stored locally in the per-user app-data folder. No data ever
leaves the machine.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import List, Optional

from .logging_setup import get_logger
from .paths import database_path

log = get_logger("database")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_sessions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_name TEXT,
    scan_mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    total_bytes INTEGER,
    scanned_bytes INTEGER,
    files_found INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recovered_files (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    original_name TEXT,
    recovered_name TEXT,
    original_path TEXT,
    file_type TEXT,
    size_bytes INTEGER,
    offset_start INTEGER,
    offset_end INTEGER,
    confidence TEXT,
    recoverability TEXT,
    destination_path TEXT,
    status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(id)
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_session ON recovered_files(session_id);
"""


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = str(path or database_path())
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        log.info("Database ready at %s", self.path)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- sessions ----------------------------------------------------------
    def save_session(self, session) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO scan_sessions
                   (id, source_id, source_name, scan_mode, started_at, completed_at,
                    status, total_bytes, scanned_bytes, files_found)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    session.session_id,
                    session.config.source_id,
                    session.config.source_name,
                    session.config.mode,
                    session.started_at or datetime.now().isoformat(timespec="seconds"),
                    session.completed_at,
                    session.status,
                    session.progress.total_bytes,
                    session.progress.scanned_bytes,
                    len(session.results),
                ),
            )
            self._conn.commit()

    def list_sessions(self, limit: int = 100) -> List[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM scan_sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM recovered_files WHERE session_id=?", (session_id,))
            self._conn.execute("DELETE FROM scan_sessions WHERE id=?", (session_id,))
            self._conn.commit()

    def clear_history(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM recovered_files")
            self._conn.execute("DELETE FROM scan_sessions")
            self._conn.commit()
        log.info("Scan history cleared by user")

    # -- recovered files ---------------------------------------------------
    def save_recovered_file(self, session_id: str, candidate, destination: str, status: str) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO recovered_files
                   (id, session_id, original_name, recovered_name, original_path,
                    file_type, size_bytes, offset_start, offset_end, confidence,
                    recoverability, destination_path, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"{session_id}:{candidate.id}",
                    session_id,
                    candidate.original_name,
                    candidate.name,
                    candidate.original_path,
                    candidate.extension,
                    candidate.size_bytes,
                    candidate.offset_start,
                    candidate.offset_end,
                    candidate.confidence,
                    candidate.recoverability,
                    destination,
                    status,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            self._conn.commit()

    # -- preferences -------------------------------------------------------
    def get_pref(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute("SELECT value FROM preferences WHERE key=?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_pref(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value) VALUES (?,?)",
                (key, value),
            )
            self._conn.commit()
