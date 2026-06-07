"""Scan orchestration.

Wires a :class:`SourceReader` to the :class:`Carver`, tracks progress, supports
pause/resume/cancel, and exposes results. The UI runs :meth:`Scanner.run` on a
background thread and consumes callbacks.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .carver import Carver, FileCandidate
from .logging_setup import get_logger
from .reader import SourceReader

log = get_logger("scanner")

MODE_QUICK = "quick"
MODE_DEEP = "deep"
MODE_LOST = "lost"
MODE_IMAGE = "image"

MODE_LABELS = {
    MODE_QUICK: "Quick Scan",
    MODE_DEEP: "Deep Scan",
    MODE_LOST: "Lost Partition Scan",
    MODE_IMAGE: "Disk Image Scan",
}


@dataclass
class ScanConfig:
    source_path: str
    source_id: str
    source_name: str
    mode: str
    size_bytes: int = 0
    sector_size: int = 512
    start_offset: int = 0
    end_offset: int = 0  # 0 -> whole source


@dataclass
class ScanProgress:
    scanned_bytes: int = 0
    total_bytes: int = 0
    files_found: int = 0
    elapsed_s: float = 0.0
    type_counts: Dict[str, int] = field(default_factory=dict)

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, self.scanned_bytes * 100.0 / self.total_bytes)

    @property
    def eta_s(self) -> float:
        if self.scanned_bytes <= 0 or self.elapsed_s <= 0:
            return 0.0
        rate = self.scanned_bytes / self.elapsed_s
        remaining = max(0, self.total_bytes - self.scanned_bytes)
        return remaining / rate if rate > 0 else 0.0


class Scanner:
    def __init__(self, config: ScanConfig):
        self.config = config
        self.session_id = f"scan_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
        self.cancel = threading.Event()
        self.pause = threading.Event()
        self.results: List[FileCandidate] = []
        self.progress = ScanProgress()
        self.status = "pending"
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self._reader: Optional[SourceReader] = None
        self._start_time = 0.0

    # -- controls ----------------------------------------------------------
    def request_cancel(self) -> None:
        self.cancel.set()

    def toggle_pause(self) -> bool:
        if self.pause.is_set():
            self.pause.clear()
            return False
        self.pause.set()
        return True

    # -- run ---------------------------------------------------------------
    def run(
        self,
        on_progress: Optional[Callable[[ScanProgress], None]] = None,
        on_found: Optional[Callable[[FileCandidate], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> List[FileCandidate]:
        cfg = self.config
        self.status = "running"
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self._start_time = time.time()

        def emit(msg: str) -> None:
            log.info(msg)
            if on_log:
                on_log(msg)

        emit(f"Starting {MODE_LABELS.get(cfg.mode, cfg.mode)} on {cfg.source_name}")
        try:
            self._reader = SourceReader(cfg.source_path, cfg.size_bytes, cfg.sector_size).open()
        except OSError as exc:
            self.status = "error"
            emit(f"ERROR: cannot open source: {exc}")
            raise

        reader = self._reader
        total = cfg.end_offset or reader.size_bytes
        if total <= 0:
            total = reader.size_bytes
        start = cfg.start_offset
        self.progress.total_bytes = total

        # Lost-partition: report detected partition/boot signatures first.
        if cfg.mode == MODE_LOST:
            for line in self._detect_partition_signatures(reader, start, total):
                emit(line)

        # Quick scan focuses on the first region for speed; others scan fully.
        if cfg.mode == MODE_QUICK:
            quick_cap = 8 * 1024 * 1024 * 1024  # 8 GiB cap for a fast pass
            total = min(total, start + quick_cap)
            self.progress.total_bytes = total
            emit("Quick scan: fast signature pass over the first region")

        carver = Carver()

        def progress_cb(abs_offset: int) -> None:
            self.progress.scanned_bytes = max(0, abs_offset - start)
            self.progress.elapsed_s = time.time() - self._start_time
            if on_progress:
                on_progress(self.progress)

        def found_cb(c: FileCandidate) -> None:
            self.results.append(c)
            self.progress.files_found = len(self.results)
            self.progress.type_counts[c.extension] = self.progress.type_counts.get(c.extension, 0) + 1
            if on_found:
                on_found(c)

        try:
            carver.scan(
                reader,
                start=start,
                end=total,
                cancel=self.cancel,
                pause=self.pause,
                progress=progress_cb,
                on_found=found_cb,
            )
        finally:
            reader.close()

        self.completed_at = datetime.now().isoformat(timespec="seconds")
        if self.cancel.is_set():
            self.status = "cancelled"
            emit("Scan cancelled by user")
        else:
            self.status = "completed"
            self.progress.scanned_bytes = self.progress.total_bytes
            if on_progress:
                on_progress(self.progress)
            emit(f"Scan complete: {len(self.results)} files found")
        if reader.bad_ranges:
            emit(f"Encountered {len(reader.bad_ranges)} bad/unreadable region(s) -> logged")
        return self.results

    # -- helpers -----------------------------------------------------------
    def _detect_partition_signatures(self, reader: SourceReader, start: int, end: int) -> List[str]:
        """Scan for boot-sector / partition signatures to hint lost partitions."""
        lines: List[str] = ["Scanning for partition / boot-sector signatures..."]
        step = 1024 * 1024  # check every 1 MiB
        found = 0
        off = start
        limit = min(end, start + 64 * 1024 * 1024 * 1024)  # cap the probe range
        while off < limit and found < 64:
            if self.cancel.is_set():
                break
            try:
                sec = reader.read_at(off, 512)
            except OSError:
                off += step
                continue
            if len(sec) >= 512 and sec[510:512] == b"\x55\xaa":
                fs = "Unknown"
                if sec[3:7] == b"NTFS":
                    fs = "NTFS"
                elif sec[3:8] == b"MSDOS" or sec[82:87] == b"FAT32":
                    fs = "FAT32"
                elif sec[3:8] == b"EXFAT":
                    fs = "exFAT"
                lines.append(f"  Boot signature at offset {off:,} (filesystem hint: {fs})")
                found += 1
            off += step
        if found == 0:
            lines.append("  No clear boot signatures found in probed range")
        return lines
