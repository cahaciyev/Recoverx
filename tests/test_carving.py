"""End-to-end carving + recovery test against a synthetic image.

Run:  python -m tests.test_carving
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recoverix.core.carver import Carver  # noqa: E402
from recoverix.core.reader import SourceReader  # noqa: E402
from recoverix.core import recovery  # noqa: E402
from recoverix.core.validation import OK, PARTIAL, validate  # noqa: E402
from scripts.make_test_image import (  # noqa: E402
    make_jpg, make_png, make_pdf, make_zip, make_bmp,
)

# A spurious "BM" that must NOT be carved as a BMP (invalid DIB header size).
_FAKE_BM = b"BM" + b"\x00" * 8 + b"\xff\xff\xff\xff" + os.urandom(64)


def build_image(path: Path, bmp: bytes) -> int:
    """Write the synthetic image; returns the byte offset of the real BMP."""
    head = b"".join([
        os.urandom(4096),
        make_jpg(), os.urandom(2048),
        make_png(), os.urandom(1024),
        make_pdf(), os.urandom(3000),
        make_zip(), os.urandom(4096),
        _FAKE_BM, os.urandom(1500),
    ])
    bmp_offset = len(head)
    # real BMP followed by trailing garbage (so its size must come from the header)
    parts = [head, bmp, os.urandom(2048)]
    path.write_bytes(b"".join(parts))
    return bmp_offset


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="recoverix_test_"))
    img = tmp / "test.img"
    bmp = make_bmp()
    bmp_offset = build_image(img, bmp)
    size = img.stat().st_size
    print(f"Test image: {img} ({size:,} bytes); BMP at offset {bmp_offset:,} ({len(bmp):,} B)")

    carver = Carver()
    with SourceReader(str(img), size, 512) as reader:
        results = carver.scan(reader, 0, size)

    found_ext = sorted({c.extension for c in results})
    print(f"Carved {len(results)} candidate(s): {found_ext}")
    for c in results:
        print(f"  - {c.name:>28} | {c.size_bytes:>7,} B | "
              f"{c.recoverability:<10} | conf={c.confidence}")

    expected = {"jpg", "png", "pdf", "bmp"}
    got = set(found_ext)
    missing = expected - got
    assert not missing, f"Missing carved types: {missing}"

    # ZIP/OOXML detection (docx extension)
    assert any(c.key == "ooxml" for c in results), "ZIP/OOXML not detected"

    # -- BMP carving correctness ------------------------------------------
    bmps = [c for c in results if c.key == "bmp"]
    assert len(bmps) == 1, f"Expected exactly 1 BMP (fakes dropped), got {len(bmps)}"
    bmp_c = bmps[0]
    assert bmp_c.offset_start == bmp_offset, "BMP carved at the wrong offset"
    assert bmp_c.size_bytes == len(bmp), (
        f"BMP size wrong: carved {bmp_c.size_bytes}, expected {len(bmp)} "
        "(must come from the header, not surrounding noise)")
    assert not any(c.offset_start == bmp_offset - len(_FAKE_BM) for c in bmps), \
        "Spurious 'BM' was incorrectly carved as a BMP"
    print(f"  BMP carved exactly ({bmp_c.size_bytes:,} B) and fake 'BM' rejected")

    # -- openability validation -------------------------------------------
    with SourceReader(str(img), size, 512) as reader:
        carved_bmp = reader.read_at(bmp_c.offset_start, bmp_c.size_bytes)
    vr = validate(carved_bmp, "bmp", "bmp")
    assert vr.status == OK, f"Carved BMP should open; got {vr.status} ({vr.detail})"
    print(f"  Openability check: BMP {vr.status} ({vr.dimensions} px)")

    # recovery (repairs + validates image/document types)
    dest = tmp / "recovered"
    res = recovery.recover_files(
        source_path=str(img), source_size=size, sector_size=512,
        candidates=results, dest_dir=str(dest),
    )
    print(f"Recovered {res.recovered}, failed {res.failed}, repaired {res.repaired}, "
          f"unopenable {res.unopenable}, bytes {res.bytes_written:,} -> {dest}")
    assert res.recovered == len(results), "Not all files recovered"
    assert res.failed == 0
    assert res.unopenable == 0, "Some recovered files do not open"

    # every recovered image must actually open with PIL
    try:
        from PIL import Image
        for f in dest.iterdir():
            if f.suffix in (".jpg", ".png", ".bmp"):
                Image.open(f).load()
                print(f"  PIL opened {f.name}")
    except ImportError:
        print("  (PIL not installed - skipping image verification)")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
