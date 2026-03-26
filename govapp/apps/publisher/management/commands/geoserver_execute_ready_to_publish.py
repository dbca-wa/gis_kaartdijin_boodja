"""Management command for Phase 2 GeoServer publishing (READY_TO_PUBLISH items)."""

# Third-Party
from django.core.management import base

# Local
from govapp.apps.publisher import geoserver_manager

# Typing
from typing import Any


class Command(base.BaseCommand):
    """Configure GeoServer for queue items that kb_geoserver_manager has placed on the shared volume."""

    help = (
        "Process READY_TO_PUBLISH GeoServerQueue items: configure GeoServer datastores/layers "
        "using file paths on the shared Docker volume (no HTTP file upload)."
    )

    def handle(self, *args: Any, **kwargs: Any) -> None:
        self.stdout.write("Processing READY_TO_PUBLISH GeoServer queue items...")
        geoserver_manager.GeoServerQueueExcutor().excute_ready_to_publish()
