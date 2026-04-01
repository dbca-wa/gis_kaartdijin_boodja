"""Management command to backfill file_size for existing LayerSubmission records.

Scans all LayerSubmission records where file_size is null and the file field is a
local path that still exists on disk, then populates file_size from the file's
actual size on disk.

Usage:
    # Dry-run (no changes written to DB):
    python manage.py backfill_layer_submission_file_size --dry-run

    # Apply changes:
    python manage.py backfill_layer_submission_file_size
"""

# Standard
import pathlib
from typing import Any

# Third-Party
from django.core.management import base

# Local
from govapp.apps.catalogue.models.layer_submissions import LayerSubmission

# Logging
import logging
log = logging.getLogger(__name__)


class Command(base.BaseCommand):
    """Backfill file_size for LayerSubmission records."""

    help = "Populate file_size for LayerSubmission records where it is missing"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be updated without writing to the database.",
        )

    def handle(self, *args: Any, **kwargs: Any) -> None:
        dry_run: bool = kwargs["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode: no changes will be saved."))

        qs = LayerSubmission.objects.filter(file_size__isnull=True).exclude(file="")

        total = qs.count()
        updated = 0
        skipped = 0

        self.stdout.write(f"Found {total} LayerSubmission record(s) with no file_size.")

        for submission in qs.iterator():
            try:
                p = pathlib.Path(submission.file)
                if not p.exists():
                    skipped += 1
                    continue

                size = p.stat().st_size
                if not dry_run:
                    LayerSubmission.objects.filter(pk=submission.pk).update(file_size=size)
                    log.info(f"Updated LayerSubmission id={submission.pk} file_size={size}")

                self.stdout.write(f"  [{'DRY' if dry_run else 'OK'}] id={submission.pk} size={size} file={submission.file}")
                updated += 1

            except (OSError, ValueError) as exc:
                self.stderr.write(f"  [SKIP] id={submission.pk} error={exc}")
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. updated={updated} skipped={skipped} total={total}"
            )
        )
