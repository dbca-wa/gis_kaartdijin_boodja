from django.core.management import base
from typing import Any
from govapp.apps.publisher.models.publish_channels import perform_geoserver_layer_health_checks


class Command(base.BaseCommand):
    # Help string
    help = "Perform Geoserver layer healthcheck"

    def handle(self, *args: Any, **kwargs: Any) -> None:
        # Display information
        self.stdout.write("Performing geoserver layer healthcheck...")

        # Go!
        perform_geoserver_layer_health_checks()