"""Generate a small synthetic disk image with embedded recoverable files.

Creates samples/disk-images/test.img containing a JPG, PNG, PDF and ZIP with
random padding (simulating free space / other data) between them. Used for
end-to-end testing of the carving engine without touching real disks.
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "disk-images" / "test.img"


def make_png() -> bytes:
    """A small, fully decodable PNG (built with Pillow)."""
    from PIL import Image  # local import: only needed when generating test data
    img = Image.new("RGBA", (24, 18))
    for x in range(24):
        for y in range(18):
            img.putpixel((x, y), ((x * 10) % 256, (y * 12) % 256, (x + y) % 256, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_jpg() -> bytes:
    """A small, fully decodable JPEG (built with Pillow)."""
    from PIL import Image  # local import: only needed when generating test data
    img = Image.new("RGB", (48, 36))
    for x in range(48):
        for y in range(36):
            img.putpixel((x, y), ((x * 5) % 256, (y * 7) % 256, (x * y) % 256))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def make_pdf() -> bytes:
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
            b"trailer<</Root 1 0 R>>\n" + os.urandom(200) + b"\n%%EOF")


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "Recoverix test payload " * 10)
    return buf.getvalue()


def make_bmp() -> bytes:
    """A small, valid 24-bit BMP (built with Pillow)."""
    from PIL import Image  # local import: only needed when generating test data
    img = Image.new("RGB", (40, 30))
    for x in range(40):
        for y in range(30):
            img.putpixel((x, y), ((x * 6) % 256, (y * 8) % 256, (x + y) % 256))
    buf = io.BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        os.urandom(4096),
        make_jpg(), os.urandom(2048),
        make_png(), os.urandom(1024),
        make_pdf(), os.urandom(3000),
        make_zip(), os.urandom(4096),
    ]
    data = b"".join(parts)
    OUT.write_bytes(data)
    print(f"Wrote {OUT} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
