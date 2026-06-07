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
from scripts.make_test_image import (  # noqa: E402
    make_jpg, make_png, make_pdf, make_zip,
)


def build_image(path: Path) -> None:
    parts = [
        os.urandom(4096),
        make_jpg(), os.urandom(2048),
        make_png(), os.urandom(1024),
        make_pdf(), os.urandom(3000),
        make_zip(), os.urandom(4096),
    ]
    path.write_bytes(b"".join(parts))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="recoverix_test_"))
    img = tmp / "test.img"
    build_image(img)
    size = img.stat().st_size
    print(f"Test image: {img} ({size:,} bytes)")

    carver = Carver()
    with SourceReader(str(img), size, 512) as reader:
        results = carver.scan(reader, 0, size)

    found_ext = sorted({c.extension for c in results})
    print(f"Carved {len(results)} candidate(s): {found_ext}")
    for c in results:
        print(f"  - {c.name:>28} | {c.size_bytes:>7,} B | "
              f"{c.recoverability:<10} | conf={c.confidence}")

    expected = {"jpg", "png", "pdf"}
    got = set(found_ext)
    missing = expected - got
    assert not missing, f"Missing carved types: {missing}"

    # ZIP/OOXML detection (docx extension)
    assert any(c.key == "ooxml" for c in results), "ZIP/OOXML not detected"

    # recovery
    dest = tmp / "recovered"
    res = recovery.recover_files(
        source_path=str(img), source_size=size, sector_size=512,
        candidates=results, dest_dir=str(dest),
    )
    print(f"Recovered {res.recovered}, failed {res.failed}, "
          f"bytes {res.bytes_written:,} -> {dest}")
    assert res.recovered == len(results), "Not all files recovered"
    assert res.failed == 0

    # validate the recovered JPEG opens with PIL if available
    try:
        from PIL import Image
        for f in dest.iterdir():
            if f.suffix == ".jpg":
                Image.open(f).verify()
                print(f"  PIL verified {f.name}")
    except ImportError:
        print("  (PIL not installed - skipping image verification)")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
