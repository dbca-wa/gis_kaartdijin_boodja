"""Management command to export a CSV report of GeoServer channels where
tile cache is enabled (create_cached_layer=True) and server cache is 0
(expire_server_cache_after_n_seconds=0).
"""

import csv
import sys
from typing import Any

from django.core.management import base

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

    def handle(self, *args: Any, **kwargs: Any) -> None:
        output_path = kwargs.get("output")

        channels = GeoServerPublishChannel.objects.filter(
            create_cached_layer=True,
            expire_server_cache_after_n_seconds=0,
        ).select_related(
            "publish_entry__catalogue_entry",
            "workspace",
            "geoserver_pool",
        ).order_by("id")

        fieldnames = [
            "channel_id",
            "layer_name",
            "workspace",
            "geoserver_pool",
            "active",
            "create_cached_layer",
            "expire_server_cache_after_n_seconds",
            "expire_client_cache_after_n_seconds",
        ]

        if output_path:
            f = open(output_path, "w", newline="", encoding="utf-8")
        else:
            f = sys.stdout  # type: ignore[assignment]

        try:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            count = 0
            for ch in channels.iterator():
                writer.writerow({
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
        finally:
            if output_path:
                f.close()

        if output_path:
            self.stdout.write(
                self.style.SUCCESS(f"Exported {count} record(s) to {output_path}.")
            )
        else:
            self.stderr.write(f"\nTotal: {count} record(s)")
