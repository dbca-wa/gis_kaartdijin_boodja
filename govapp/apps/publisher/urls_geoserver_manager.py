"""URL configuration for the kb_geoserver_manager API."""

# Third-Party
from rest_framework import routers

# Local
from govapp.apps.publisher.views_geoserver_manager import GeoServerManagerQueueViewSet


router = routers.DefaultRouter()
router.register("layers", GeoServerManagerQueueViewSet, basename="geoserver-manager-layers")

urlpatterns = router.urls
