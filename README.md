# Recoverix — Professional Desktop Data Recovery

A safe, **read-only** data recovery application for Windows. Recoverix scans
disks, removable media and disk images and recovers deleted / formatted / lost
files using signature-based file carving. It ships as a **single `.exe`**.

> Recovery is never guaranteed. Recoverix never writes to the source disk.

## Features

- **Device detection** — physical disks, USB drives, SD cards, partitions and disk images.
- **Accurate disk health (SMART)** — reads raw ATA SMART and NVMe health logs *directly* from the
  device (Win32 `DeviceIoControl` via a native C++ helper + a ctypes fallback), so health reflects
  real reallocated/pending/uncorrectable sectors and NVMe endurance — not the coarse Windows
  "Healthy" flag. Rebuild the helper with `native\build_helper.bat` (needs MSVC).
- **Scan modes** — Quick, Deep (raw carving), Lost Partition, and Disk Image.
- **File carving** — JPG, PNG, GIF, BMP, TIFF, WEBP, PDF, DOC/XLS/PPT, DOCX/XLSX/PPTX,
  ZIP, RAR, 7Z, GZ, MP3, WAV, FLAC, MP4/MOV/M4A, AVI, MKV, WMV, SQLite and more.
- **Recoverability scoring** — Excellent / Good / Average / Poor / Unknown + High/Medium/Low confidence.
- **Openability check** — verifies a carved file actually opens (images decoded with Pillow,
  PDFs/ZIP-based docs structurally checked) and shows Opens / Partial / Won't-open per file.
- **Auto-repair** — fixes common carving damage before writing: correct BMP size field,
  full ZIP/OOXML End-Of-Central-Directory, trailing-garbage trim on JPG/PNG/GIF/BMP.
- **Preview** — images (via Pillow), text/CSV/JSON/XML, plus format, size, dimensions and open-status.
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

**One-click:** double-click **`build.bat`** (installs deps + builds).

Or from a terminal:

```bash
pip install -r requirements.txt
python build.py
# -> dist/Recoverix.exe
```

The build uses PyInstaller `--onefile --windowed --uac-admin`, so the produced
`Recoverix.exe` is fully self-contained.

### Run on any computer — no Python, no install

`dist/Recoverix.exe` bundles the Python runtime and every dependency. Copy that
**single file** to any Windows 10/11 PC and double-click it — nothing needs to be
installed on the target machine. It requests Administrator rights (UAC) on launch
so it can read physical disks; that is a one-time prompt, not an installation.

> **Tip:** because the `.exe` is unsigned, Windows SmartScreen may show
> *"Windows protected your PC"* the first time. Click **More info → Run anyway**.
> To remove the warning entirely, sign the `.exe` with a code-signing certificate.

> Built and verified on Python 3.14 with PyInstaller 6.20. Requirements use `>=`
> pins so the build keeps working on newer Python releases.

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
