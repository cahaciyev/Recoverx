"""Read-only source reader.

Provides safe, read-only streaming access to three kinds of sources:

* Physical drives          ``\\\\.\\PhysicalDrive0``
* Logical volumes          ``\\\\.\\C:``
* Disk image files         ``C:\\path\\disk.img``

The reader NEVER opens a source for writing. Raw devices are read with
sector-aligned requests, and unreadable (bad) sectors are retried then skipped
so a damaged disk can never crash a scan.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

from .logging_setup import get_logger

log = get_logger("reader")

DEFAULT_SECTOR = 512


@dataclass
class BadRange:
    offset: int
    length: int


class SourceReader:
    """Read-only reader for a physical device, volume or image file."""

    def __init__(self, path: str, size_bytes: int = 0, sector_size: int = DEFAULT_SECTOR):
        self.path = path
        self.is_raw = path.startswith("\\\\.\\") or path.startswith("//./")
        self.sector_size = sector_size if sector_size > 0 else DEFAULT_SECTOR
        self._fd: Optional[int] = None
        self.bad_ranges: List[BadRange] = []
        self.size_bytes = size_bytes
        self.max_read_retries = 2

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> "SourceReader":
        flags = os.O_RDONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY  # Windows: avoid text translation
        self._fd = os.open(self.path, flags)
        if not self.size_bytes:
            self.size_bytes = self._detect_size()
        log.info("Opened source %s (size=%d bytes, raw=%s)", self.path, self.size_bytes, self.is_raw)
        return self

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def __enter__(self) -> "SourceReader":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # -- sizing ------------------------------------------------------------
    def _detect_size(self) -> int:
        assert self._fd is not None
        try:
            cur = os.lseek(self._fd, 0, os.SEEK_CUR)
            end = os.lseek(self._fd, 0, os.SEEK_END)
            os.lseek(self._fd, cur, os.SEEK_SET)
            if end > 0:
                return end
        except OSError:
            pass
        # Raw devices may not report size via seek; caller should supply it.
        return 0

    # -- raw reads ---------------------------------------------------------
    def _raw_read_aligned(self, offset: int, length: int) -> bytes:
        """Read for raw devices using sector-aligned offset/length."""
        assert self._fd is not None
        ss = self.sector_size
        aligned_off = (offset // ss) * ss
        head = offset - aligned_off
        total = head + length
        aligned_len = ((total + ss - 1) // ss) * ss
        os.lseek(self._fd, aligned_off, os.SEEK_SET)
        data = os.read(self._fd, aligned_len)
        return data[head:head + length]

    def read_at(self, offset: int, length: int) -> bytes:
        """Read ``length`` bytes at ``offset`` (read-only). Returns possibly short data."""
        if self._fd is None:
            raise RuntimeError("reader not opened")
        if self.is_raw:
            return self._raw_read_aligned(offset, length)
        os.lseek(self._fd, offset, os.SEEK_SET)
        return os.read(self._fd, length)

    # -- streaming ---------------------------------------------------------
    def iter_blocks(
        self,
        start: int,
        end: int,
        block_size: int = 4 * 1024 * 1024,
        cancel: Optional[threading.Event] = None,
        pause: Optional[threading.Event] = None,
        progress=None,
    ) -> Iterator[Tuple[int, bytes]]:
        """Yield ``(offset, data)`` blocks from ``start`` to ``end``.

        Bad sectors are retried then skipped (filled with zeros) so the scan
        continues and offsets stay consistent. Pausing waits on ``pause``;
        cancelling stops the iteration cleanly.
        """
        if self.is_raw:
            block_size = (block_size // self.sector_size) * self.sector_size or self.sector_size
        offset = start
        while offset < end:
            if cancel is not None and cancel.is_set():
                log.info("Scan cancelled at offset %d", offset)
                return
            if pause is not None:
                while pause.is_set():
                    if cancel is not None and cancel.is_set():
                        return
                    threading.Event().wait(0.1)

            want = min(block_size, end - offset)
            data = self._safe_block(offset, want)
            if data:
                yield offset, data
            if progress is not None:
                progress(offset + want)
            offset += want

    def _safe_block(self, offset: int, length: int) -> bytes:
        """Read a block, retrying bad sectors and zero-filling skipped ones."""
        for attempt in range(self.max_read_retries + 1):
            try:
                data = self.read_at(offset, length)
                if len(data) < length:
                    # short read near a defect / end of media: pad to keep alignment
                    data = data + b"\x00" * (length - len(data))
                return data
            except OSError as exc:
                if attempt < self.max_read_retries:
                    continue
                log.warning("Bad read at offset %d len %d: %s -> skipping", offset, length, exc)
                self.bad_ranges.append(BadRange(offset, length))
                return b"\x00" * length
        return b"\x00" * length
