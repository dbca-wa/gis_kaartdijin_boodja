"""Kaartdijin Boodja Catalogue Django Application Command Views."""


# Standard
import logging

# Third-Party
from django import conf
from django.core import management
from drf_spectacular import utils as drf_utils
from rest_framework import decorators
from rest_framework import request
from rest_framework import response
from rest_framework import routers
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

# Local
from govapp.apps.accounts import permissions
from govapp.common.utils import UserGroupServiceNotFoundError

# Logging
log = logging.getLogger(__name__)


@drf_utils.extend_schema(tags=["Management Commands"])
class ManagementCommands(viewsets.ViewSet):
    """Management Commands View Set."""
    permission_classes = [permissions.IsInAdministratorsGroup]

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def scan(self, request: request.Request) -> response.Response:
        """Runs the `scan` Management Command.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            # Run Management Command
            # Here, instead of directly running the `scan` management command
            # we run it via the `runcrons` command. This allows us to take
            # advantage of the builtin locking functionality - i.e., we won't
            # be able to run the scanner if its already running. The `--force`
            # option is used to allow us to call the scanner whenever we want,
            # but it does not bypass the concurrency locking.
            management.call_command("runcrons", conf.settings.CRON_SCANNER_CLASS, "--force")

        except Exception as exc:
            # Log
            log.error(f"Unable to perform scan: {exc}")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def randomize_password(self, request: request.Request) -> response.Response:
        try:
            management.call_command("runcrons", "govapp.apps.catalogue.cron.DirectoryScannerCronJob", "--force")
        except Exception as exc:
            # Log
            log.error(f"Unable to perform randomize_password: {exc}")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def scan_dir(self, request: request.Request) -> response.Response:
        """Runs the `scan` Management Command.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            # Run Management Command
            # Here, instead of directly running the `scan` management command
            # we run it via the `runcrons` command. This allows us to take
            # advantage of the builtin locking functionality - i.e., we won't
            # be able to run the scanner if its already running. The `--force`
            # option is used to allow us to call the scanner whenever we want,
            # but it does not bypass the concurrency locking.
            management.call_command("runcrons", "govapp.apps.catalogue.cron.DirectoryScannerCronJob", "--force")

        except Exception as exc:
            # Log
            log.error(f"Unable to perform scan: {exc}")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def get_sharepoint_submissions(self, request: request.Request) -> response.Response:
        """Runs the `scan` Management Command.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            # Run Management Command
            # Here, instead of directly running the `scan` management command
            # we run it via the `runcrons` command. This allows us to take
            # advantage of the builtin locking functionality - i.e., we won't
            # be able to run the scanner if its already running. The `--force`
            # option is used to allow us to call the scanner whenever we want,
            # but it does not bypass the concurrency locking.
            management.call_command("runcrons", "govapp.apps.catalogue.cron.SharepointScannerCronJob", "--force")

        except Exception as exc:
            # Log
            log.error(f"Unable to perform scan: {exc}")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def get_postgis_submissions(self, request: request.Request) -> response.Response:
        try:
            management.call_command("runcrons", "govapp.apps.catalogue.cron.PostgresScannerCronJob", "--force")
        except Exception as exc:
            log.error(f"Unable to perform scan: {exc}")

        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def excute_geoserver_queue(self, request: request.Request) -> response.Response:
        """Runs the `geoserver queue` Management Command.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            management.call_command("runcrons", "govapp.apps.publisher.cron.PublishGeoServerQueueCronJob", "--force")

        except Exception as exc:
            # Log
            log.error(f"Unable to perform scan: {exc}")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def excute_itassets_users_sync(self, request: request.Request) -> response.Response:
        """Runs the `geoserver queue` Management Command.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            management.call_command("runcrons", "govapp.apps.accounts.cron.ItassetsUsersSyncCronJob", "--force")

        except Exception as exc:
            # Log
            log.error(f"Unable to perform itassets users sync: {exc}")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def excute_geoserver_sync(self, request: request.Request) -> response.Response:
        """Runs the `geoserver sync` Management Command.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            # Run Management Command
            if 'items_to_sync' not in request.data:
                raise ValidationError("frequency_type is required")

            items_to_sync = request.data.get('items_to_sync')
            if items_to_sync == 'layers':
                management.call_command("geoserver_sync_layers")
            elif items_to_sync == 'roles':
                management.call_command("geoserver_sync_roles")
            elif items_to_sync == 'groups':
                management.call_command("geoserver_sync_groups")
            elif items_to_sync == 'rules':
                management.call_command("geoserver_sync_rules")
            elif items_to_sync == 'users':
                # A person asked for a sync, so sync even when the KB data has not changed
                management.call_command("sync_users", force=True)
            else:
                raise ValidationError('Invalid items_to_sync value')
            # Return Response
            return response.Response(status=status.HTTP_204_NO_CONTENT)

        except ValidationError as e:
            # Handle validation errors separately
            log.error(f"Validation error: {e}")
            return response.Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except UserGroupServiceNotFoundError as e:
            # Handle custom HttpStatusError
            log.error(f"HTTP status error: {e}")
            return response.Response({'detail': str(e), 'error': str(e)}, status=e.status_code)
        except Exception as e:
            # Handle unexpected exceptions
            log.error(f"Unexpected error: {e}")
            # If the exception has a status_code attribute, use it; otherwise, use 500
            status_code = getattr(e, 'status_code', status.HTTP_500_INTERNAL_SERVER_ERROR)
            return response.Response({'detail': 'Internal server error', 'error': str(e)}, status=status_code)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def geoserver_auto_enqueue(self, request: request.Request) -> response.Response:
        """Runs the `geoserver_auto_enqueue` Management Command.

        This command identifies eligible publish entries based on active channels with enabled GeoServer pools
        and automatically adds them to the GeoServer processing queue.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Handle Errors
        try:
            # Run the geoserver_auto_enqueue command directly
            management.call_command("geoserver_auto_enqueue")
            
        except Exception as exc:
            # Log
            log.error(f"Unable to perform auto enqueue: {exc}")
            return response.Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=False, methods=["POST"])
    def perform_geoserver_layer_healthcheck(self, request: request.Request) -> response.Response:
        try:
            # All health check levels, so every layer is checked once
            management.call_command("geoserver_layer_health_check")
        except Exception as exc:
            log.error(f"Unable to perform scan: {exc}")

        return response.Response(status=status.HTTP_204_NO_CONTENT)

    
# Router
router = routers.DefaultRouter()
router.register("commands", ManagementCommands, basename="commands")

# Commands URL Patterns
urlpatterns = router.urls
