"""Management command to clean up duplicate DECLINED LayerSubmission records.

When a large GIS file is uploaded, a cron race condition (now fixed) could
create multiple DECLINED LayerSubmission records for the same CatalogueEntry,
each with its own copy of the source file archived in data_storage/.

This command deletes those DECLINED, inactive LayerSubmission records and their
associated files, leaving only the valid SUBMITTED / ACCEPTED records untouched.

Usage:
    # Dry-run (default - no changes made):
    python manage.py cleanup_duplicate_submissions --catalogue-entry-id 1211

    # Execute the actual deletion:
    python manage.py cleanup_duplicate_submissions --catalogue-entry-id 1211 --execute
"""

# Standard
import os
import pathlib
from typing import Any

# Third-Party
from django.core.management import base
from django.db import transaction
from django.utils import timezone as django_timezone

# Local
from govapp.apps.catalogue.models.catalogue_entries import CatalogueEntry
from govapp.apps.catalogue.models.layer_submissions import LayerSubmission, LayerSubmissionStatus

# Logging
import logging
log = logging.getLogger(__name__)


class Command(base.BaseCommand):
    """Delete duplicate DECLINED LayerSubmission records and their archived files."""

    help = (
        "Remove duplicate DECLINED LayerSubmission records (and their archived files) "
        "for a given CatalogueEntry.  Only inactive, DECLINED records are targeted; "
        "SUBMITTED, ACCEPTED, and is_active=True records are never touched."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--catalogue-entry-id",
            type=int,
            required=True,
            metavar="ID",
            help="Primary key of the CatalogueEntry whose duplicate submissions should be removed.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help="Actually perform the deletion.  Without this flag the command runs in dry-run mode.",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_size(self, size_bytes: int) -> str:
        """Return a human-readable file size string."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 ** 3:
            return f"{size_bytes / 1024 ** 2:.1f} MB"
        return f"{size_bytes / 1024 ** 3:.2f} GB"

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def handle(self, *args: Any, **kwargs: Any) -> None:
        catalogue_entry_id: int = kwargs["catalogue_entry_id"]
        execute: bool = kwargs["execute"]

        # ----------------------------------------------------------------
        # 1. Verify the CatalogueEntry exists
        # ----------------------------------------------------------------
        try:
            catalogue_entry = CatalogueEntry.objects.get(pk=catalogue_entry_id)
        except CatalogueEntry.DoesNotExist:
            raise base.CommandError(
                f"CatalogueEntry with id={catalogue_entry_id} does not exist."
            )

        self.stdout.write(
            f"CatalogueEntry: [{catalogue_entry.pk}] {catalogue_entry.name}  "
            f"(status={catalogue_entry.get_status_display()})"
        )
        self.stdout.write("")

        # ----------------------------------------------------------------
        # 2. Find target records
        #    Only DECLINED + is_active=False submissions are targeted.
        #    SUBMITTED, ACCEPTED, and is_active=True are never touched.
        # ----------------------------------------------------------------
        candidates = LayerSubmission.objects.filter(
            catalogue_entry_id=catalogue_entry_id,
            status=LayerSubmissionStatus.DECLINED,
            is_active=False,
        ).order_by("submitted_at")

        # Safety check: warn if any DECLINED record is somehow active (should not happen)
        active_declined = LayerSubmission.objects.filter(
            catalogue_entry_id=catalogue_entry_id,
            status=LayerSubmissionStatus.DECLINED,
            is_active=True,
        )
        if active_declined.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"WARNING: {active_declined.count()} DECLINED submission(s) have "
                    "is_active=True — these will NOT be touched."
                )
            )

        total_candidates = candidates.count()

        if total_candidates == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "No inactive DECLINED submissions found for this CatalogueEntry.  Nothing to do."
                )
            )
            return

        # ----------------------------------------------------------------
        # 3. Report what will be / was deleted
        # ----------------------------------------------------------------
        mode_label = "DRY-RUN" if not execute else "EXECUTE"
        self.stdout.write(
            self.style.WARNING(
                f"[{mode_label}] Found {total_candidates} inactive DECLINED submission(s) to remove:"
            )
        )
        self.stdout.write("")

        total_freed_bytes: int = 0
        files_found: int = 0
        files_missing: int = 0

        rows = []
        for submission in candidates:
            file_path = pathlib.Path(submission.file) if submission.file else None
            file_exists = file_path is not None and file_path.is_file()
            file_size_bytes = file_path.stat().st_size if file_exists else 0

            if file_exists:
                files_found += 1
                total_freed_bytes += file_size_bytes
            elif file_path is not None:
                files_missing += 1

            rows.append((submission, submission.pk, file_path, file_exists, file_size_bytes))

            # Print one line per submission (full path so operator can verify before executing)
            # Use localtime so the displayed timestamp matches what the operator sees in the UI.
            local_submitted_at = django_timezone.localtime(submission.submitted_at)
            self.stdout.write(
                f"  LM{submission.pk:04d} | submitted={local_submitted_at.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            if file_path:
                exist_tag = "EXISTS" if file_exists else "MISSING"
                size_tag = self._format_size(file_size_bytes) if file_exists else "—"
                self.stdout.write(
                    f"          file=[{exist_tag}] {size_tag}  {file_path}"
                )
            else:
                self.stdout.write("          file=<empty>")

        self.stdout.write("")
        self.stdout.write(
            f"  Files on disk : {files_found} found, {files_missing} missing"
        )
        self.stdout.write(
            f"  Disk to free  : {self._format_size(total_freed_bytes)}"
        )
        self.stdout.write(
            f"  DB records    : {total_candidates}"
        )
        self.stdout.write("")

        # ----------------------------------------------------------------
        # 4. Dry-run ends here
        # ----------------------------------------------------------------
        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run complete.  No changes were made.  "
                    "Re-run with --execute to perform the actual deletion."
                )
            )
            return

        # ----------------------------------------------------------------
        # 5. Execute: delete DB records first (in a transaction), then files
        #
        # Order of operations is critical:
        #   a) All DB records are deleted inside a single atomic transaction.
        #      If any DB deletion fails, the transaction rolls back and NO
        #      records are deleted, and NO files are touched.
        #   b) Files are deleted only after the transaction has committed.
        #      If a file deletion fails, the DB record is already gone — the
        #      orphaned file on disk is harmless and can be removed manually.
        #
        # This is safer than the reverse order (file first, then DB), which
        # could leave DB records pointing to non-existent files if the DB
        # delete fails unexpectedly.
        # ----------------------------------------------------------------
        self.stdout.write(self.style.WARNING("Executing deletion..."))

        # Phase A: delete all DB records in one atomic transaction.
        # Inside the transaction, each record's status is re-verified before deletion.
        # If any record has been modified since the dry-run (e.g. promoted to SUBMITTED
        # by another process), the entire transaction rolls back and no files are touched.
        try:
            with transaction.atomic():
                for submission, pk, _file_path, _file_exists, _file_size_bytes in rows:
                    # Re-fetch from DB with a row-level lock to prevent races.
                    current = LayerSubmission.objects.select_for_update().get(pk=pk)
                    if current.status != LayerSubmissionStatus.DECLINED or current.is_active:
                        raise base.CommandError(
                            f"LayerSubmission pk={pk} is no longer DECLINED+inactive "
                            f"(current status={current.get_status_display()}, "
                            f"is_active={current.is_active}). "
                            f"Aborting — transaction rolled back, no records or files deleted."
                        )
                    current.delete()
                    log.info(
                        "cleanup_duplicate_submissions: deleted LayerSubmission pk=%d", pk,
                    )
        except base.CommandError:
            raise
        except Exception as exc:
            raise base.CommandError(
                f"Database deletion failed and was rolled back — no records were deleted "
                f"and no files were touched.  Error: {exc}"
            )

        deleted_records = len(rows)
        self.stdout.write(f"  {deleted_records} DB record(s) deleted.")

        # Phase B: delete files now that DB transaction has committed
        deleted_files: int = 0
        skipped_files: int = 0
        freed_bytes: int = 0

        for _submission, pk, file_path, file_exists, file_size_bytes in rows:
            if file_path is None:
                continue
            if not file_exists:
                log.warning(
                    "cleanup_duplicate_submissions: file not found on disk (DB record already deleted): %s "
                    "(LayerSubmission pk=%d)",
                    file_path, pk,
                )
                skipped_files += 1
                continue
            try:
                os.remove(file_path)
                deleted_files += 1
                freed_bytes += file_size_bytes
                log.info(
                    "cleanup_duplicate_submissions: deleted file %s "
                    "(LayerSubmission pk=%d)", file_path, pk,
                )
            except OSError as exc:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ERROR: could not delete file {file_path}: {exc}  "
                        f"(LayerSubmission pk={pk})"
                        f" — DB record already deleted; file must be removed manually."
                    )
                )
                skipped_files += 1

        # ----------------------------------------------------------------
        # 6. Summary
        # ----------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(f"  DB records deleted : {deleted_records}")
        self.stdout.write(f"  Files deleted      : {deleted_files}")
        if skipped_files:
            self.stdout.write(
                self.style.WARNING(f"  Files not deleted  : {skipped_files} (see errors/warnings above — remove manually)")
            )
        self.stdout.write(f"  Disk freed         : {self._format_size(freed_bytes)}")
