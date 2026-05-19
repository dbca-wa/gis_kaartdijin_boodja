# Fix: Duplicate Layer Submissions for Large Files

## Problem

When a large GIS file (e.g. 16.5 GB) is uploaded to `pending_imports/`, the directory scanner
cron job creates multiple duplicate `LayerSubmission` records — all `DECLINED` — before finally
creating a successful one.

## Root Cause

`move_to_storage()` in `govapp/common/local_storage.py` uses `shutil.copyfile()` followed by
`os.unlink()` to archive a file from `pending_imports/` to `data_storage/`. For large files,
`shutil.copyfile()` blocks for several minutes. During that time the original file remains in
`pending_imports/`, and subsequent cron runs keep finding it and creating new submissions.

Contributing factors:

- `DIRECTORY_SCANNER_PERIOD_MINS = 2` — scanner runs every 2 minutes.
- `DJANGO_CRON_LOCK_TIME = 10` — the django-cron cache lock expires after only **10 seconds**
  (the comment in `settings.py` incorrectly describes this as minutes; the implementation in
  `django_cron/backends/lock/cache.py` treats it as seconds). The lock therefore expires long
  before a large-file copy finishes, allowing the next 2-minute cycle to start a new job.
- `pending_imports/` and `data_storage/` are mounted as **separate subPath mount points** of the
  same Azure Files PVC in Kubernetes. Because they are different mount points, `os.rename()`
  across them raises `EXDEV` (cross-device link), so replacing `shutil.copyfile()` with
  `shutil.move()` alone is insufficient — `shutil.move()` would fall back to copy + delete,
  leaving the race condition in place.

The cascade of `DECLINED` statuses occurs because once the first duplicate submission causes the
`CatalogueEntry` to enter `DECLINED` status, every subsequent submission is also declined by the
`activate()` logic in `LayerSubmission`.

## Fix

Three files require changes.

### 1. `govapp/common/local_storage.py`

Replace `print(e)` with a proper logger call. The `shutil.copyfile()` + `os.unlink()` pattern is
intentionally kept: `shutil.copyfile()` copies file content only (no metadata), which is
important for Azure Files (SMB) compatibility — metadata operations performed by `shutil.copy2()`
or `shutil.move()` can raise errors on Azure Files. The race condition is fully addressed by the
`.absorbing` rename in `directory_absorber.py` above; no change to the copy mechanism is needed.

### 2. `govapp/apps/catalogue/directory_absorber.py` — `absorb()` method

Before calling `move_to_storage()`, atomically rename the file within `pending_imports/` to
`<filename>.<ext>.absorbing`. Because both the source and destination of this rename are on the
same mount point, the operation is a fast metadata update (not a data copy). The original stem
and suffix are captured before the rename so that `storage_path` is computed correctly.

If the rename fails (e.g. another cron job already claimed the file), log and return immediately
to avoid a duplicate.

### 3. `govapp/apps/catalogue/directory_scanner.py`

Add `.absorbing` to the skip list alongside `.tmp` and `.tmp.size` so that in-progress files
are never picked up by a concurrent scan.

## Flow After Fix

```
T+0s   Scanner finds filename.gpkg
       absorb() renames it to filename.gpkg.absorbing  ← atomic, ~milliseconds
       move_to_storage() begins copying to data_storage/ (may take minutes)

T+2m   Scanner runs again, finds filename.gpkg.absorbing → SKIPPED
T+4m   Scanner runs again → SKIPPED
  …
T+Nm   copy completes, filename.gpkg.absorbing deleted from pending_imports/
       process_file() runs → exactly one LayerSubmission created
```

## Edge Case

If the process crashes between the rename and the completion of `move_to_storage()`, the file
`filename.gpkg.absorbing` will remain in `pending_imports/` indefinitely. Recovery requires
manually renaming or removing it. This is far preferable to the current behaviour of creating
dozens of duplicate submissions.

## Files Changed

| File | Change |
|---|---|
| `govapp/common/local_storage.py` | `shutil.move()`, logger |
| `govapp/apps/catalogue/directory_absorber.py` | Rename to `.absorbing` before copy |
| `govapp/apps/catalogue/directory_scanner.py` | Skip `.absorbing` files |
