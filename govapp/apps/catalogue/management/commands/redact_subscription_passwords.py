"""Management command to redact plaintext passwords from ActionsLogEntry records.

Scans all ActionsLogEntry.what fields that contain 'userpassword' and replaces
the plaintext password value with '***'.

Usage:
    # Dry-run (no changes written to DB):
    python manage.py redact_subscription_passwords --dry-run

    # Apply changes:
    python manage.py redact_subscription_passwords
"""

# Standard
import re
from typing import Any

# Third-Party
from django.core.management import base
from django.db import transaction

# Local
from govapp.apps.logs.models import ActionsLogEntry

# Matches both single-quoted and double-quoted password values produced by
# Python's str(dict), e.g.:
#   'userpassword': 'secret'
#   'userpassword': "secret"
#   "userpassword": 'secret'
#   "userpassword": "secret"
# The value group (group 2) captures 1+ characters so that empty passwords
# ('userpassword': '') are deliberately left unchanged.
_PATTERN = re.compile(
    r"""(['"]\s*userpassword\s*['"]\s*:\s*['"])([^'"]+)(['"])""",
    re.IGNORECASE,
)


def _redact(text: str) -> tuple[str, bool]:
    """Return (redacted_text, was_changed)."""
    redacted = _PATTERN.sub(r"\g<1>***\g<3>", text)
    return redacted, redacted != text


class Command(base.BaseCommand):
    """Redact plaintext passwords stored in ActionsLogEntry records."""

    help = "Redact userpassword values stored in ActionsLogEntry.what fields"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be changed without writing to the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN mode: no changes will be saved."))

        # Only fetch rows that actually contain 'userpassword' — avoids a full
        # table scan on large deployments.
        qs = ActionsLogEntry.objects.filter(what__icontains="userpassword")
        total = qs.count()
        self.stdout.write(f"Found {total} ActionsLogEntry record(s) containing 'userpassword'.")

        changed_count = 0
        skipped_count = 0  # already redacted

        with transaction.atomic():
            for entry in qs:
                redacted, was_changed = _redact(entry.what)

                if not was_changed:
                    skipped_count += 1
                    self.stdout.write(
                        f"  [SKIP] id={entry.id} — already redacted or pattern did not match."
                    )
                    continue

                self.stdout.write(f"  [{'DRY' if dry_run else 'UPDATE'}] id={entry.id}")

                if not dry_run:
                    entry.what = redacted
                    entry.save(update_fields=["what"])
                    changed_count += 1
                else:
                    changed_count += 1

            if dry_run:
                # Roll back even if something slipped through — safety net.
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. {'Would update' if dry_run else 'Updated'} {changed_count} record(s), "
                f"skipped {skipped_count} record(s)."
            )
        )
