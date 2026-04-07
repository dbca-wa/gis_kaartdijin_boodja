"""Management command to export a CSV report of GeoServer channels where
tile cache is enabled (create_cached_layer=True) and server cache is 0
(expire_server_cache_after_n_seconds=0).

Usage:
    python manage.py export_tilecache_report [--output FILE] [--group GROUP]

Arguments:
    --output FILE   Write the CSV report to FILE. If omitted, CSV is printed to stdout.
    --group GROUP   Send the CSV report by email to all active users in GROUP.
                    Defaults to the TILECACHE_REPORT_GROUP environment variable,
                    which itself defaults to 'Tile Cache Report'.
                    Pass an empty string (--group "") to suppress email sending.

Examples:
    # Print CSV to stdout and email to the default group ('Tile Cache Report')
    python manage.py export_tilecache_report

    # Save CSV to a file and email to the default group
    python manage.py export_tilecache_report --output /tmp/report.csv

    # Print CSV to stdout only (no email)
    python manage.py export_tilecache_report --group ""

    # Save CSV to a file only (no email)
    python manage.py export_tilecache_report --output /tmp/report.csv --group ""

    # Print CSV to stdout and email to a specific group
    python manage.py export_tilecache_report --group "GIS Admins"

Environment variables:
    TILECACHE_REPORT_GROUP  Override the default email recipient group name.
                            Default: 'Tile Cache Report'
    EMAIL_DELIVERY          Must be set to 'on' for emails to actually be sent.
                            Default: 'off'
"""

import csv
import io
import sys
from typing import Any

import decouple
from django.contrib.auth.models import Group
from django.core.management import base

from govapp import settings

from govapp.apps.publisher.emails import TileCacheReportEmail
from govapp.apps.publisher.models.publish_channels import GeoServerPublishChannel


class Command(base.BaseCommand):
    help = (
        "Export a CSV report of GeoServer publish channels where tile cache is "
        "enabled and expire_server_cache_after_n_seconds is 0."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--output",
            default=None,
            help="Output CSV file path. Defaults to stdout.",
        )
        parser.add_argument(
            "--group",
            default=decouple.config("TILECACHE_REPORT_GROUP", default=settings.GROUP_TILECACHE_REPORT),
            help="Django auth group name. All active users in this group will receive the report by email. Defaults to TILECACHE_REPORT_GROUP env var.",
        )

    def handle(self, *args: Any, **kwargs: Any) -> None:
        output_path = kwargs.get("output")
        group_name = kwargs.get("group")

        channels = GeoServerPublishChannel.objects.filter(
            create_cached_layer=True,
            expire_server_cache_after_n_seconds=0,
        ).select_related(
            "publish_entry__catalogue_entry",
            "workspace",
            "geoserver_pool",
        ).order_by("id")

        fieldnames = [
            "catalogue_id",
            "publish_id",
            "channel_id",
            "layer_name",
            "workspace",
            "geoserver_pool",
            "active",
            "create_cached_layer",
            "expire_server_cache_after_n_seconds",
            "expire_client_cache_after_n_seconds",
        ]

        # Always build the CSV in memory so it can be both saved and emailed
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()

        count = 0
        for ch in channels.iterator():
            writer.writerow({
                "catalogue_id": ch.publish_entry.catalogue_entry_id,
                "publish_id": ch.publish_entry_id,
                "channel_id": ch.id,
                "layer_name": ch.name,
                "workspace": str(ch.workspace),
                "geoserver_pool": str(ch.geoserver_pool) if ch.geoserver_pool else "",
                "active": ch.active,
                "create_cached_layer": ch.create_cached_layer,
                "expire_server_cache_after_n_seconds": ch.expire_server_cache_after_n_seconds,
                "expire_client_cache_after_n_seconds": ch.expire_client_cache_after_n_seconds,
            })
            count += 1

        csv_content = csv_buffer.getvalue()

        if output_path:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                f.write(csv_content)
            self.stdout.write(
                self.style.SUCCESS(f"Exported {count} record(s) to {output_path}.")
            )
        else:
            sys.stdout.write(csv_content)
            self.stderr.write(f"\nTotal: {count} record(s)")

        if group_name:
            try:
                group = Group.objects.get(name=group_name)
            except Group.DoesNotExist:
                self.stderr.write(
                    self.style.ERROR(f"Group '{group_name}' does not exist.")
                )
                return

            recipients = list(
                group.user_set.filter(is_active=True).exclude(email="").values_list("email", flat=True)
            )
            if not recipients:
                self.stderr.write(
                    self.style.WARNING(
                        f"Group '{group_name}' has no active members with an email address."
                    )
                )
                return

            email = TileCacheReportEmail()
            email.send(
                to_addresses=recipients,
                context={"count": count},
                attachments=[("tilecache_report.csv", csv_content.encode("utf-8"), "text/csv")],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Report emailed to {len(recipients)} recipient(s) in group '{group_name}'."
                )
            )
