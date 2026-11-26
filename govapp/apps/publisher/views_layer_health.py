"""View for the layer health API (for monitoring tools such as PRTG).

    GET /api/layer-health/?level=critical

Returns the layers of the active channels whose last health check failed:

    {"status": "down", "count": 2, "layers": ["workspace:layer", ...]}

status is "down" if count > 0, otherwise "up". level is optional (critical, business_hours,
non_critical; several separated by commas). Without it, all levels are counted.

Authentication: the same as the kb_geoserver_manager API (views_geoserver_manager).
    Production (DEBUG=False): Auth2 handles Basic Auth; the user must be in the 'API User' group.
    Development (DEBUG=True): authentication is skipped (AllowAny).
"""

# Third-Party
from django.conf import settings
from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

# Local
from govapp.apps.accounts.permissions import IsApiUser
from govapp.apps.publisher.models.publish_channels import HealthCheckLevel, get_unhealthy_channels
from govapp.apps.publisher.views_geoserver_manager import SSOMiddlewareAuthentication


class LayerHealthView(views.APIView):
    """Unhealthy layers, optionally filtered by health check level."""

    authentication_classes = [] if settings.DEBUG else [SSOMiddlewareAuthentication]
    permission_classes = [AllowAny] if settings.DEBUG else [IsApiUser]

    def get(self, request):
        levels = []
        for name in request.query_params.get("level", "").split(","):
            name = name.strip()
            if not name:
                continue
            try:
                levels.append(HealthCheckLevel[name.upper()])
            except KeyError:
                valid_names = ", ".join(level.name.lower() for level in HealthCheckLevel)
                return Response(
                    {"detail": f"Unknown level: {name}. Use one or more of: {valid_names}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        layers = sorted(channel.layer_name_with_workspace for channel in get_unhealthy_channels(levels))
        return Response({
            "status": "down" if layers else "up",
            "count": len(layers),
            "layers": layers,
        })
