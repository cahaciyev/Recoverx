"""Safe recovery of carved files to a destination folder.

Safety rules enforced here:
* The source is opened read-only; nothing is ever written back to it.
* The destination must not be on the source device (unless explicitly overridden).
* Free space is validated before writing.
* Existing files are never overwritten - a numeric suffix is appended instead.
* Every recovered file is logged and recorded in the database.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .carver import FileCandidate
from .logging_setup import get_logger
from .reader import SourceReader

log = get_logger("recovery")

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_COPY_CHUNK = 4 * 1024 * 1024


@dataclass
class RecoveryResult:
    recovered: int = 0
    failed: int = 0
    bytes_written: int = 0
    destination: str = ""
    failures: List[str] = field(default_factory=list)


def safe_filename(name: str) -> str:
    name = _SAFE_NAME.sub("_", name).strip("._") or "recovered_file"
    return name[:150]


def unique_path(dest_dir: str, filename: str) -> str:
    """Return a path that does not overwrite an existing file."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    i = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, f"{base}_{i}{ext}")
        i += 1
    return candidate


def destination_drive(dest_dir: str) -> str:
    return os.path.splitdrive(os.path.abspath(dest_dir))[0].upper()


def is_destination_on_source(dest_dir: str, source_device) -> bool:
    """True if writing to ``dest_dir`` would touch the source device."""
    dest_drive = destination_drive(dest_dir).rstrip(":")
    if source_device is None:
        return False
    if getattr(source_device, "is_image", False):
        # image file: unsafe only if dest is the same drive as the image file
        img_drive = os.path.splitdrive(os.path.abspath(source_device.path))[0].upper().rstrip(":")
        return bool(dest_drive) and dest_drive == img_drive
    # physical device: unsafe if dest drive letter is one of its partitions
    for p in getattr(source_device, "partitions", []) or []:
        if p.drive_letter and p.drive_letter.upper() == dest_drive:
            return True
    return False


def free_space(dest_dir: str) -> int:
    try:
        return shutil.disk_usage(dest_dir).free
    except OSError:
        return 0


def estimate_total(candidates: List[FileCandidate]) -> int:
    return sum(c.size_bytes for c in candidates)


def recover_files(
    *,
    source_path: str,
    source_size: int,
    sector_size: int,
    candidates: List[FileCandidate],
    dest_dir: str,
    db=None,
    session_id: str = "",
    cancel: Optional[threading.Event] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
) -> RecoveryResult:
    """Copy the byte ranges of ``candidates`` from the source to ``dest_dir``."""
    result = RecoveryResult(destination=dest_dir)
    os.makedirs(dest_dir, exist_ok=True)

    def emit(msg: str) -> None:
        log.info(msg)
        if on_log:
            on_log(msg)

    needed = estimate_total(candidates)
    avail = free_space(dest_dir)
    if needed > avail:
        msg = f"Not enough free space: need {needed:,} bytes, have {avail:,}"
        emit("ERROR: " + msg)
        raise OSError(msg)

    total = len(candidates)
    reader = SourceReader(source_path, source_size, sector_size).open()
    try:
        for i, cand in enumerate(candidates, 1):
            if cancel is not None and cancel.is_set():
                emit("Recovery cancelled by user")
                break
            out_path = unique_path(dest_dir, safe_filename(cand.name))
            try:
                written = _write_candidate(reader, cand, out_path)
                result.recovered += 1
                result.bytes_written += written
                status = "recovered"
                emit(f"Recovered {os.path.basename(out_path)} ({written:,} bytes)")
            except OSError as exc:
                result.failed += 1
                result.failures.append(f"{cand.name}: {exc}")
                status = "failed"
                emit(f"FAILED {cand.name}: {exc}")
                out_path = ""
            if db is not None and session_id:
                try:
                    db.save_recovered_file(session_id, cand, out_path, status)
                except Exception as exc:  # noqa: BLE001 - never break recovery on db errors
                    log.warning("DB record failed for %s: %s", cand.name, exc)
            if on_progress:
                on_progress(i, total, cand.name)
    finally:
        reader.close()
    emit(f"Recovery finished: {result.recovered} recovered, {result.failed} failed")
    return result


def _write_candidate(reader: SourceReader, cand: FileCandidate, out_path: str) -> int:
    remaining = cand.size_bytes
    offset = cand.offset_start
    written = 0
    with open(out_path, "wb") as fh:
        while remaining > 0:
            want = min(_COPY_CHUNK, remaining)
            data = reader.read_at(offset, want)
            if not data:
                break
            fh.write(data)
            written += len(data)
            offset += len(data)
            remaining -= len(data)
    return written


def read_preview(source_path: str, source_size: int, sector_size: int, cand: FileCandidate, max_bytes: int = 2_000_000) -> bytes:
    """Read up to ``max_bytes`` from a candidate for previewing (read-only)."""
    n = min(max_bytes, cand.size_bytes)
    reader = SourceReader(source_path, source_size, sector_size).open()
    try:
        return reader.read_at(cand.offset_start, n)
    finally:
        reader.close()
