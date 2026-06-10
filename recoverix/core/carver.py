"""Signature-based file carving engine (deep scan).

The carver streams the source read-only, detects known file headers (handling
boundaries between blocks), then resolves each file's end using a footer,
a format-specific length field, or the next header as an upper bound. It applies
max-size limits so files without footers never scan forever.
"""
from __future__ import annotations

import struct
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .logging_setup import get_logger
from .reader import SourceReader
from .scoring import score_carved
from .signatures import Signature, load_signatures
from .validation import bmp_file_size

log = get_logger("carver")

MIN_FILE_SIZE = 48  # bytes; ignore tiny header-only noise


@dataclass
class FileCandidate:
    id: str
    key: str
    extension: str
    category: str
    offset_start: int
    offset_end: int
    confidence: str
    recoverability: str
    footer_found: bool
    validated: bool
    original_name: Optional[str] = None
    original_path: Optional[str] = None
    open_status: str = ""   # set once the file is validated (Openable/Partial/Corrupt)

    @property
    def size_bytes(self) -> int:
        return self.offset_end - self.offset_start

    @property
    def name(self) -> str:
        if self.original_name:
            return self.original_name
        return f"recovered_{self.id}.{self.extension}"

    @property
    def preview_available(self) -> bool:
        return self.category in ("Images", "Documents") or self.extension in (
            "txt", "csv", "json", "xml", "log", "rtf",
        )


def _find_all(hay: bytes, needle: bytes, start: int = 0):
    if not needle:
        return
    idx = hay.find(needle, start)
    while idx != -1:
        yield idx
        idx = hay.find(needle, idx + 1)


class Carver:
    def __init__(self, signatures: Optional[List[Signature]] = None):
        self.signatures = signatures or load_signatures()
        self._by_key: Dict[str, Signature] = {s.key: s for s in self.signatures}
        # generic byte headers -> signatures (excludes container-special types)
        self._header_index: List[tuple[bytes, Signature]] = []
        for s in self.signatures:
            if s.riff or s.ftyp:
                continue
            for h in s.headers:
                self._header_index.append((h, s))
        self._max_pattern = max((len(h) for h, _ in self._header_index), default=8)
        self._max_pattern = max(self._max_pattern, 12)  # room for 'ftyp'/'RIFF'

    # -- public API --------------------------------------------------------
    def scan(
        self,
        reader: SourceReader,
        start: int,
        end: int,
        cancel: Optional[threading.Event] = None,
        pause: Optional[threading.Event] = None,
        progress: Optional[Callable[[int], None]] = None,
        on_found: Optional[Callable[[FileCandidate], None]] = None,
        block_size: int = 4 * 1024 * 1024,
    ) -> List[FileCandidate]:
        """Carve files from ``[start, end)``. Returns resolved candidates."""
        raw_hits = self._detect_headers(reader, start, end, cancel, pause, progress, block_size)
        raw_hits.sort(key=lambda h: h[0])
        log.info("Header detection complete: %d raw hits", len(raw_hits))

        candidates: List[FileCandidate] = []
        offsets_only = [h[0] for h in raw_hits]
        max_accept_end = -1
        counter = 0
        for i, (off, sig, form_ext) in enumerate(raw_hits):
            if cancel is not None and cancel.is_set():
                break
            if off < max_accept_end:
                continue  # inside a previously accepted file -> skip noise
            next_off = end
            for j in range(i + 1, len(offsets_only)):
                if offsets_only[j] > off:
                    next_off = offsets_only[j]
                    break
            cand = self._resolve(reader, off, sig, form_ext, end, next_off)
            if cand is None:
                continue
            counter += 1
            cand.id = f"{counter:06d}"
            candidates.append(cand)
            max_accept_end = max(max_accept_end, cand.offset_end)
            if on_found is not None:
                on_found(cand)
        log.info("Carving produced %d candidate files", len(candidates))
        return candidates

    # -- header detection --------------------------------------------------
    def _detect_headers(self, reader, start, end, cancel, pause, progress, block_size):
        hits: List[tuple[int, Signature, Optional[str]]] = []
        carry = b""
        carry_len = self._max_pattern - 1
        for block_off, data in reader.iter_blocks(
            start, end, block_size=block_size, cancel=cancel, pause=pause, progress=progress
        ):
            buf = carry + data
            base = block_off - len(carry)
            # generic headers
            for needle, sig in self._header_index:
                for idx in _find_all(buf, needle):
                    hits.append((base + idx, sig, None))
            # RIFF containers (webp/wav/avi) share 'RIFF' magic
            for idx in _find_all(buf, b"RIFF"):
                if idx + 12 <= len(buf):
                    form = buf[idx + 8:idx + 12]
                    sig = self._riff_sig(form)
                    if sig is not None:
                        hits.append((base + idx, sig, None))
            # ISO-BMFF (mp4/mov/m4a): '....ftyp'
            for idx in _find_all(buf, b"ftyp"):
                if idx >= 4:
                    sig = self._by_key.get("mp4")
                    if sig is not None:
                        hits.append((base + idx - 4, sig, None))
            carry = buf[-carry_len:] if len(buf) >= carry_len else buf
        return hits

    def _riff_sig(self, form: bytes) -> Optional[Signature]:
        for s in self.signatures:
            if s.riff and s.riff.encode("ascii", "ignore") == form:
                return s
        return None

    # -- size resolution ---------------------------------------------------
    def _resolve(self, reader, off, sig: Signature, form_ext, end_limit, next_off) -> Optional[FileCandidate]:
        max_end = min(off + sig.max_size, end_limit)
        footer_found = False
        validated = False
        file_end: Optional[int] = None

        # BMP: validate the header and compute the exact size from pixel
        # geometry. This both drops the many false "BM" matches in random data
        # and stops real bitmaps being truncated at a later spurious "BM".
        if sig.key == "bmp":
            true_size = bmp_file_size(reader.read_at(off, 54))
            if true_size is None:
                return None  # not a real BMP header -> discard noise
            file_end = min(off + true_size, max_end)
            validated = (off + true_size) <= max_end  # False -> truncated by media end
        else:
            # 1) format-specific exact length
            file_end = self._format_length(reader, off, sig, max_end)
            if file_end is not None:
                validated = True

        # 2) footer search
        if file_end is None and sig.footers:
            file_end, footer_found = self._search_footer(reader, off, sig, min(max_end, next_off + len(max(sig.footers, key=len)) if next_off < max_end else max_end))
            if file_end is not None:
                # ZIP/OOXML: the footer marks the START of the End-Of-Central-
                # Directory record. Extend to include the full EOCD (+comment)
                # so the archive actually opens.
                if sig.key == "ooxml":
                    file_end = self._extend_eocd(reader, file_end, max_end)
                validated = self._validate(reader, off, file_end, sig)

        # 3) bound by next header / max size
        if file_end is None:
            file_end = min(max_end, next_off if next_off > off else max_end)

        size = file_end - off
        if size < MIN_FILE_SIZE:
            return None

        in_bad = self._overlaps_bad(reader, off, file_end)
        confidence, recoverability = score_carved(
            footer_found=footer_found,
            validated=validated,
            size=size,
            min_size=MIN_FILE_SIZE,
            max_size=sig.max_size,
            in_bad_range=in_bad,
        )
        return FileCandidate(
            id="",
            key=sig.key,
            extension=form_ext or sig.extension,
            category=sig.category,
            offset_start=off,
            offset_end=file_end,
            confidence=confidence,
            recoverability=recoverability,
            footer_found=footer_found,
            validated=validated,
        )

    def _format_length(self, reader, off, sig: Signature, max_end) -> Optional[int]:
        try:
            if sig.riff:
                hdr = reader.read_at(off, 12)
                if len(hdr) >= 8 and hdr[:4] == b"RIFF":
                    size = struct.unpack_from("<I", hdr, 4)[0]
                    cand_end = off + 8 + size
                    if off < cand_end <= max_end:
                        return cand_end
            if sig.ftyp or sig.key == "mp4":
                return self._mp4_length(reader, off, max_end)
        except (OSError, struct.error):
            return None
        return None

    def _mp4_length(self, reader, off, max_end) -> Optional[int]:
        """Walk ISO-BMFF top-level boxes to find the file end."""
        pos = off
        steps = 0
        while pos < max_end and steps < 4096:
            steps += 1
            hdr = reader.read_at(pos, 16)
            if len(hdr) < 8:
                break
            box_size = struct.unpack_from(">I", hdr, 0)[0]
            box_type = hdr[4:8]
            if box_size == 1:
                if len(hdr) < 16:
                    break
                box_size = struct.unpack_from(">Q", hdr, 8)[0]
            if box_size < 8 or not all(32 <= b < 127 for b in box_type):
                break
            pos += box_size
        if pos > off + 8 and pos <= max_end:
            return pos
        return None

    def _search_footer(self, reader, off, sig: Signature, max_end):
        chunk = 8 * 1024 * 1024
        pos = off + len(sig.headers[0]) if sig.headers else off + 4
        best_footer = max(sig.footers, key=len)
        overlap = len(best_footer) - 1
        carry = b""
        carry_base = pos
        while pos < max_end:
            want = min(chunk, max_end - pos)
            data = reader.read_at(pos, want)
            if not data:
                break
            buf = carry + data
            best_idx = -1
            best_len = 0
            for f in sig.footers:
                idx = buf.find(f)
                if idx != -1 and (best_idx == -1 or idx < best_idx):
                    best_idx = idx
                    best_len = len(f)
            if best_idx != -1:
                file_end = carry_base + best_idx + best_len
                return file_end, True
            carry = buf[-overlap:] if overlap > 0 else b""
            carry_base = pos + want - len(carry)
            pos += want
        return None, False

    def _extend_eocd(self, reader, footer_end: int, max_end: int) -> int:
        """Grow a ZIP/OOXML end so it spans the whole End-Of-Central-Directory.

        ``footer_end`` points just past the 4-byte ``PK\\x05\\x06`` signature.
        The EOCD record is 22 bytes plus a trailing comment; truncating it makes
        the archive unreadable, so we read its comment length and extend.
        """
        eocd_start = footer_end - 4
        rec = reader.read_at(eocd_start, 22)
        if len(rec) >= 22 and rec[:4] == b"PK\x05\x06":
            comment_len = struct.unpack_from("<H", rec, 20)[0]
            return min(eocd_start + 22 + comment_len, max_end)
        return footer_end

    def _validate(self, reader, off, file_end, sig: Signature) -> bool:
        try:
            head = reader.read_at(off, 16)
            if sig.key == "jpg":
                return head[:3] == b"\xff\xd8\xff"
            if sig.key == "png":
                return head[:8] == b"\x89PNG\r\n\x1a\n"
            if sig.key == "ooxml":
                return head[:4] == b"PK\x03\x04"
            if sig.key == "pdf":
                return head[:4] == b"%PDF"
        except OSError:
            return False
        return True

    def _overlaps_bad(self, reader: SourceReader, start, end) -> bool:
        for br in reader.bad_ranges:
            if br.offset < end and (br.offset + br.length) > start:
                return True
        return False
