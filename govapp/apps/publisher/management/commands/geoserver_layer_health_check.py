from django.core.management import base
from typing import Any
from govapp.apps.publisher.models.publish_channels import HealthCheckLevel, perform_geoserver_layer_health_checks


class Command(base.BaseCommand):
    # Help string
    help = "Perform Geoserver layer healthcheck"

    def add_arguments(self, parser: base.CommandParser) -> None:
        parser.add_argument(
            "--level",
            choices=[level.name.lower() for level in HealthCheckLevel],
            help="Check only the layers of this health check level. Without it, all layers are checked.",
        )

    def handle(self, *args: Any, **kwargs: Any) -> None:
        # Display information
        self.stdout.write("Performing geoserver layer healthcheck...")

        # Go!
        level = kwargs.get("level")
        perform_geoserver_layer_health_checks(HealthCheckLevel[level.upper()] if level else None)
