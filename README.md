# Recoverix — Professional Desktop Data Recovery

A safe, **read-only** data recovery application for Windows. Recoverix scans
disks, removable media and disk images and recovers deleted / formatted / lost
files using signature-based file carving. It ships as a **single `.exe`**.

> Recovery is never guaranteed. Recoverix never writes to the source disk.

## Features

- **Device detection** — physical disks, USB drives, SD cards, partitions and disk images.
- **Scan modes** — Quick, Deep (raw carving), Lost Partition, and Disk Image.
- **File carving** — JPG, PNG, GIF, BMP, TIFF, WEBP, PDF, DOC/XLS/PPT, DOCX/XLSX/PPTX,
  ZIP, RAR, 7Z, GZ, MP3, WAV, FLAC, MP4/MOV/M4A, AVI, MKV, WMV, SQLite and more.
- **Recoverability scoring** — Excellent / Good / Average / Poor / Unknown + High/Medium/Low confidence.
- **Preview** — images (via Pillow) and text/CSV/JSON/XML before recovery.
- **Safe recovery** — same-disk protection, free-space checks, no overwrite (auto-suffix).
- **History & reports** — SQLite scan history; export JSON/TXT recovery reports.
- **Bad-sector tolerant** — retries then skips unreadable sectors; never crashes on a damaged disk.
- **Private** — 100% offline, no telemetry, logs stored locally.

## Project layout

```
Recoverix/
├── main.py                  # launcher (PyInstaller entry point)
├── build.py                 # one-command single-exe build
├── requirements.txt
├── recoverix/
│   ├── core/                # engine: reader, carver, scanner, recovery, devices, db
│   ├── ui/                  # CustomTkinter UI + screens
│   └── resources/           # signatures.json
├── scripts/make_test_image.py
├── tests/test_carving.py
└── docs/
```

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

Run as **Administrator** to access physical disks. Disk-image scanning needs no elevation.

## Build the single .exe

```bash
pip install -r requirements.txt
python build.py
# -> dist/Recoverix.exe
```

The build uses PyInstaller `--onefile --windowed --uac-admin`, so the produced
`Recoverix.exe` is self-contained and requests Administrator rights for physical
disk access.

## Test the engine

```bash
python -m tests.test_carving        # carves + recovers from a synthetic image
python scripts/make_test_image.py   # writes samples/disk-images/test.img to try in the UI
```

## Safety & limitations

- Sources are always opened **read-only**; nothing is written back to them.
- Never recover files to the **same disk** you are scanning.
- Overwritten data cannot be recovered. **SSD TRIM** may make recovery impossible.
- Physically damaged drives may need a lab. For failing drives, image first, then scan the image.
- Fragmented large files may recover only partially (carving assumes contiguous data).

## License

MIT — see [LICENSE](LICENSE).
