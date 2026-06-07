# Recoverix Architecture

Recoverix is a single-process Python desktop app. The **engine** (pure Python,
no UI dependencies) is cleanly separated from the **UI** (CustomTkinter).

```
recoverix/
├── core/                     ← engine (importable & testable without a GUI)
│   ├── paths.py              writable app-data / resource path resolution
│   ├── logging_setup.py      rotating local log files
│   ├── signatures.py         embedded file-signature database (source of truth)
│   ├── reader.py             read-only SourceReader (devices, volumes, images)
│   ├── carver.py             header detection + size resolution (carving)
│   ├── scoring.py            confidence + recoverability grading
│   ├── scanner.py            orchestration, progress, pause/resume/cancel
│   ├── recovery.py           safe export with destination guards
│   ├── devices.py            PowerShell-based device/partition enumeration
│   └── database.py           SQLite sessions / files / preferences
└── ui/
    ├── app.py                window, navigation, shared state, threading
    ├── theme.py, widgets.py  look & feel
    └── screens/              welcome → device → mode → progress → results → dest → complete
```

## Data flow

1. **devices.list_devices()** enumerates disks via PowerShell Storage cmdlets.
2. The user selects a device/partition/image → `ScanConfig`.
3. **Scanner.run()** opens a read-only `SourceReader` and drives the **Carver**:
   - `Carver._detect_headers` streams blocks (with a carry buffer for boundary
     straddling) and records header offsets, including RIFF and ISO-BMFF containers.
   - `Carver._resolve` finds each file's end via a format length field, a footer
     search, or the next header as an upper bound, capped by `maxSize`.
   - `scoring.score_carved` grades each candidate.
4. The UI polls `Scanner.progress` on the Tk main thread (`after`) while the scan
   runs on a worker thread.
5. **recovery.recover_files()** re-reads the chosen byte ranges read-only and
   writes them to a destination on a *different* disk, enforcing safety rules.

## Threading model

- Scans and recovery run on daemon worker threads.
- The UI never touches engine objects destructively; it reads progress snapshots
  and schedules widget updates via `widget.after(...)`.
- `threading.Event` objects provide cooperative cancel/pause.

## Why Python + PyInstaller

A single self-contained `.exe` with `--onefile --uac-admin` gives read-only raw
device access (`\\.\PhysicalDriveN`, `\\.\C:`) and a modern UI without a separate
native engine. The engine is structured so a faster native carver could later be
swapped in behind the same `Carver` interface.
