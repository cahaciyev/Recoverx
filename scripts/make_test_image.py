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
    # 1x1 transparent PNG
    return bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4"
        "890000000A49444154789C6360000002000100FFFF03000006000557BFABD400"
        "00000049454E44AE426082"
    )


def make_jpg() -> bytes:
    # minimal but structurally valid JPEG (header...EOI)
    body = bytes.fromhex(
        "FFD8FFE000104A46494600010100000100010000FFDB004300080606070605080707"
        "07090908"
    )
    body += os.urandom(400)
    return body + b"\xff\xd9"


def make_pdf() -> bytes:
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
            b"trailer<</Root 1 0 R>>\n" + os.urandom(200) + b"\n%%EOF")


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "Recoverix test payload " * 10)
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
