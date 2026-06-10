"""Openability validation and best-effort repair for carved files.

A carved file is only useful if it actually opens. Carving resolves byte
ranges from raw media, which can leave a file truncated or padded with
trailing garbage (a common reason a recovered ``.bmp`` "recovers" but won't
open). This module:

* :func:`validate` - decodes/checks carved bytes and reports whether the file
  *Opens correctly*, is only *Partially* readable, or is *Corrupt*.
* :func:`repair`   - fixes common, safe-to-correct damage (wrong BMP size
  field, trailing garbage after an image's end marker) so the written file
  opens in normal viewers.

Everything here is pure/in-memory and never touches the source media.
"""
from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass
from typing import Optional

try:  # Pillow is optional; image validation degrades to UNKNOWN without it.
    from PIL import Image, ImageFile
    _HAS_PIL = True
except Exception:  # noqa: BLE001
    _HAS_PIL = False

# -- openability status ----------------------------------------------------
OK = "Openable"        # decodes fully
PARTIAL = "Partial"    # opens but truncated / only partly readable
CORRUPT = "Corrupt"    # cannot be opened
UNKNOWN = "Unknown"    # type we do not validate (or Pillow missing)

# Full-decode validation is bounded so we never load a huge file into memory.
MAX_VALIDATE_BYTES = 96 * 1024 * 1024

_IMAGE_KEYS = {"jpg", "png", "gif", "bmp", "tiff", "webp"}
_BMP_DIB_SIZES = {12, 40, 52, 56, 64, 108, 124}


@dataclass
class ValidationResult:
    status: str
    detail: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    subtype: Optional[str] = None  # image mode, "zip", etc.

    @property
    def openable(self) -> bool:
        return self.status in (OK, PARTIAL)

    @property
    def dimensions(self) -> str:
        if self.width and self.height:
            return f"{self.width} x {self.height}"
        return ""


# -- BMP geometry (shared by the carver and the repairer) ------------------
def bmp_file_size(hdr: bytes) -> Optional[int]:
    """Return the true BMP file size computed from its header.

    Returns ``None`` when *hdr* is not a structurally valid BMP header - the
    carver uses this to drop the many false ``"BM"`` (0x42 0x4D) matches that
    occur in random data. The size is derived from the pixel geometry rather
    than the ``bfSize`` field, which real-world encoders often leave as ``0``.
    """
    if len(hdr) < 26 or hdr[:2] != b"BM":
        return None
    bf_offbits = struct.unpack_from("<I", hdr, 10)[0]
    dib = struct.unpack_from("<I", hdr, 14)[0]
    if dib not in _BMP_DIB_SIZES:
        return None
    try:
        if dib == 12:  # BITMAPCOREHEADER
            width = struct.unpack_from("<H", hdr, 18)[0]
            height = struct.unpack_from("<H", hdr, 20)[0]
            planes = struct.unpack_from("<H", hdr, 22)[0]
            bpp = struct.unpack_from("<H", hdr, 24)[0]
            bi_size_image = 0
        else:
            if len(hdr) < 38:
                return None
            width = struct.unpack_from("<i", hdr, 18)[0]
            height = struct.unpack_from("<i", hdr, 22)[0]
            planes = struct.unpack_from("<H", hdr, 26)[0]
            bpp = struct.unpack_from("<H", hdr, 28)[0]
            bi_size_image = struct.unpack_from("<I", hdr, 34)[0]
    except struct.error:
        return None

    if planes != 1 or bpp not in (1, 4, 8, 16, 24, 32):
        return None
    if not (0 < width <= 100_000):
        return None
    abs_h = abs(height)
    if not (0 < abs_h <= 100_000):
        return None

    row = ((width * bpp + 31) // 32) * 4          # rows padded to 4 bytes
    pixels = row * abs_h
    if bi_size_image and bi_size_image >= pixels:  # honour explicit (often for RLE)
        pixels = bi_size_image

    if 14 + dib <= bf_offbits < 1_000_000:         # trust a plausible data offset
        data_start = bf_offbits
    else:                                          # else header + palette
        palette = (1 << bpp) * 4 if bpp <= 8 else 0
        data_start = 14 + dib + palette
    return data_start + pixels


# -- validation ------------------------------------------------------------
def validate(data: bytes, key: str, extension: str) -> ValidationResult:
    """Report whether *data* opens as a *key*/*extension* file."""
    if not data:
        return ValidationResult(CORRUPT, "Empty file")
    if len(data) > MAX_VALIDATE_BYTES:
        # Too large to fully decode here; validate the header only.
        return _validate_header_only(data, key)

    if key in _IMAGE_KEYS or extension in _IMAGE_KEYS:
        return _validate_image(data)
    if key == "pdf" or extension == "pdf":
        return _validate_pdf(data)
    if key == "ooxml" or extension in ("zip", "docx", "xlsx", "pptx"):
        return _validate_zip(data)
    return ValidationResult(UNKNOWN, "No content check for this type")


def _validate_image(data: bytes) -> ValidationResult:
    if not _HAS_PIL:
        return ValidationResult(UNKNOWN, "Pillow not available")
    prev = getattr(ImageFile, "LOAD_TRUNCATED_IMAGES", False)
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        try:
            with Image.open(io.BytesIO(data)) as im:
                w, h, mode = im.width, im.height, im.mode
                im.load()  # force a full decode
            return ValidationResult(OK, "Opens correctly", w, h, mode)
        except Exception as strict_exc:  # noqa: BLE001
            # Retry tolerantly: a truncated-but-viewable image is still useful.
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            try:
                with Image.open(io.BytesIO(data)) as im:
                    w, h, mode = im.width, im.height, im.mode
                    im.load()
                return ValidationResult(
                    PARTIAL, f"Partially readable ({_short(strict_exc)})", w, h, mode)
            except Exception as exc:  # noqa: BLE001
                return ValidationResult(CORRUPT, f"Cannot be opened ({_short(exc)})")
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = prev


def _validate_pdf(data: bytes) -> ValidationResult:
    if not data.startswith(b"%PDF"):
        return ValidationResult(CORRUPT, "Missing %PDF header")
    if b"%%EOF" in data[-2048:]:
        return ValidationResult(OK, "Has PDF header and trailer", subtype="pdf")
    if b"%%EOF" in data:
        return ValidationResult(PARTIAL, "Trailer present but trailing data after it", subtype="pdf")
    return ValidationResult(PARTIAL, "PDF header found but no %%EOF trailer", subtype="pdf")


def _validate_zip(data: bytes) -> ValidationResult:
    if not data.startswith(b"PK\x03\x04"):
        return ValidationResult(CORRUPT, "Missing ZIP local header")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            bad = zf.testzip()
            names = zf.namelist()
        if bad is not None:
            return ValidationResult(PARTIAL, f"Some entries corrupt (first: {bad})", subtype="zip")
        return ValidationResult(OK, f"Valid archive, {len(names)} entr(ies)", subtype="zip")
    except zipfile.BadZipFile as exc:
        return ValidationResult(CORRUPT, f"Cannot be opened ({_short(exc)})", subtype="zip")
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(PARTIAL, f"Archive only partly readable ({_short(exc)})", subtype="zip")


def _validate_header_only(data: bytes, key: str) -> ValidationResult:
    """Cheap header sanity for files too large to fully decode."""
    if key == "bmp":
        return (ValidationResult(OK, "Valid BMP header (large file)")
                if bmp_file_size(data[:54]) else ValidationResult(CORRUPT, "Invalid BMP header"))
    if _HAS_PIL and key in _IMAGE_KEYS:
        try:
            with Image.open(io.BytesIO(data)) as im:
                return ValidationResult(OK, "Header valid (large file)", im.width, im.height, im.mode)
        except Exception as exc:  # noqa: BLE001
            return ValidationResult(PARTIAL, f"Header only ({_short(exc)})")
    return ValidationResult(UNKNOWN, "Large file - not fully validated")


# -- repair ----------------------------------------------------------------
def repair(data: bytes, key: str, extension: str) -> tuple[bytes, bool]:
    """Return ``(possibly_fixed_bytes, changed)``.

    Repairs are conservative: they only correct the BMP size field and trim
    trailing garbage that follows a known end marker. Bytes are never invented,
    so a repaired file is always a subset/relabelling of the carved data.
    """
    try:
        if key == "bmp":
            return _repair_bmp(data)
        if key == "jpg":
            return _trim_after(data, b"\xff\xd9")
        if key == "png":
            return _trim_after(data, b"IEND\xaeB`\x82")
        if key == "gif":
            return _trim_after(data, b"\x00\x3b")
    except Exception:  # noqa: BLE001 - repair must never break recovery
        return data, False
    return data, False


def _repair_bmp(data: bytes) -> tuple[bytes, bool]:
    size = bmp_file_size(data[:54])
    if not size:
        return data, False
    changed = False
    if len(data) > size:           # drop trailing garbage carved past the image
        data = data[:size]
        changed = True
    # Correct the bfSize field so strict viewers accept the file.
    if len(data) >= 6 and struct.unpack_from("<I", data, 2)[0] != len(data):
        data = data[:2] + struct.pack("<I", len(data)) + data[6:]
        changed = True
    return data, changed


def _trim_after(data: bytes, marker: bytes) -> tuple[bytes, bool]:
    idx = data.rfind(marker)
    if idx == -1:
        return data, False
    end = idx + len(marker)
    if end < len(data):
        return data[:end], True
    return data, False


def _short(exc: object, limit: int = 80) -> str:
    s = str(exc).strip().replace("\n", " ")
    return s[:limit] if s else exc.__class__.__name__
