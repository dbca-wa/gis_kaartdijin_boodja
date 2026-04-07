"""Kaartdijin Boodja Publisher Django Application URLs."""


# Third-Party
from rest_framework import routers
from django.urls import path, re_path

# Local
from govapp.apps.publisher import views


# Router
router = routers.DefaultRouter()
router.register("entries", views.PublishEntryViewSet)
router.register("channels/cddp", views.CDDPPublishChannelViewSet)
router.register("channels/ftp", views.FTPPublishChannelViewSet)
router.register("channels/ftp-server", views.FTPServerViewSet)
router.register("channels/geoserver", views.GeoServerPublishChannelViewSet)
router.register("notifications/emails", views.EmailNotificationViewSet)
router.register("workspaces", views.WorkspaceViewSet)
router.register("geoserverweb", views.GeoServerQueueViewSet)
router.register("cddp-contents", views.CDDPContentsViewSet, basename='cddp-contents')
router.register("geoservergroup", views.GeoServerGroupViewSet)
router.register("geoserver_layer_healthcheck", views.GeoServerLayerHealthcheckViewSet, basename='geoserver-layer-healthcheck')

# The re_path patterns below make trailing slashes optional for the cddp-contents actions.
# This is a defensive measure: callers that construct URLs with os.path.join() or strip trailing
# slashes would otherwise trigger a 301 redirect that converts DELETE to GET (405).  The current
# Windows sync script already appends trailing slashes correctly, but these patterns make the
# API robust against future clients or direct API calls that omit them.
urlpatterns = router.urls + [
    re_path(
        r'^cddp-contents/delete-file/?$',
        views.CDDPContentsViewSet.as_view({'delete': 'destroy_file'}),
        name='cddp-contents-delete-file-noslash',
    ),
    re_path(
        r'^cddp-contents/retrieve-file/?$',
        views.CDDPContentsViewSet.as_view({'get': 'retrieve_file'}),
        name='cddp-contents-retrieve-file-noslash',
    ),
]
