# Safety Rules

Recoverix is built to be safe-by-default. These rules are enforced in code.

## Source protection (read-only)

- `SourceReader` opens every source with `O_RDONLY` (`recoverix/core/reader.py`).
  There is no write path to a source anywhere in the engine.
- Raw devices are read with sector-aligned requests.

## Destination protection

Enforced in `recoverix/core/recovery.py`:

1. The destination must not be on the source device. `is_destination_on_source`
   compares the destination drive letter against the source's partitions (or the
   image file's drive). The UI shows a red danger banner and requires an explicit
   override checkbox to proceed.
2. Free space is validated before any bytes are written (`free_space` vs.
   `estimate_total`); insufficient space aborts with a clear error.
3. Existing files are never overwritten — `unique_path` appends `_1`, `_2`, …
4. File names are sanitised (`safe_filename`).
5. Every recovered file is logged and recorded in SQLite.

## Damaged media

- Bad sectors are retried (`max_read_retries`) then skipped and zero-filled so the
  scan continues; bad ranges are logged and reduce a file's recoverability score.
- For failing / SMR drives the UI recommends creating a disk image first and
  scanning the image.

## SSD / TRIM

- SSDs are detected from `MediaType`; the UI warns that TRIM may have permanently
  erased deleted data. Recoverix never promises guaranteed recovery.

## Privacy

- Fully offline. No network calls, no telemetry. Logs, history and preferences are
  stored only under `%LOCALAPPDATA%\Recoverix`.
