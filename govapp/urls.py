"""Kaartdijin Boodja URL Configuration.

The `urlpatterns` list routes URLs to views.
For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/

Examples:
    Function views
        1. Add an import:  from my_app import views
        2. Add a URL to urlpatterns:  path("", views.home, name="home")
    Class-based views
        1. Add an import:  from other_app.views import Home
        2. Add a URL to urlpatterns:  path("", Home.as_view(), name="home")
    Including another URLconf
        1. Import the include() function: from django.urls import include, path
        2. Add a URL to urlpatterns:  path("blog/", include("blog.urls"))
"""


# Third-Party
from django import conf
from django import urls
from django.contrib import admin
from django.contrib.auth import views as auth_views

# Local
from govapp import views
from govapp.apps.accounts.views import FileDeleteView, FileDownloadView, FileListView


# Admin Site Settings
admin.site.site_header = conf.settings.PROJECT_TITLE
admin.site.index_title = conf.settings.PROJECT_TITLE
admin.site.site_title = conf.settings.PROJECT_TITLE

# To test sentry
def trigger_error(request):
    division_by_zero = 1 / 0  # noqa

# Django URL Patterns
urlpatterns = [
    # Home Page
    urls.path("", views.HomePage.as_view(), name="home"),

    # Django Administration
    urls.path("admin/", admin.site.urls),

    # API Endpoints
    urls.path("api/accounts/", urls.include("govapp.apps.accounts.urls")),
    urls.path("api/docs/", urls.include("govapp.apps.swagger.urls")),
    urls.path("api/catalogue/", urls.include("govapp.apps.catalogue.urls")),
    urls.path("api/logs/", urls.include("govapp.apps.logs.urls")),
    urls.path("api/publish/", urls.include("govapp.apps.publisher.urls")),
    urls.path("api/geoserver-manager/", urls.include("govapp.apps.publisher.urls_geoserver_manager")),

    # Management Command Endpoints
    urls.path("api/management/", urls.include("govapp.commands")),
    
    # Templates Pages
    urls.re_path("management-commands/", views.ManagementCommandsView.as_view()),
    urls.path("pending-imports/", views.PendingImportsView.as_view()),
    # Publish
    urls.path("publish/", views.PublishPage.as_view()),
    urls.re_path("publish/(?P<pk>\d+)/", views.PublishView.as_view()),

    # Catalogue    
    urls.path("catalogue/entries/", views.CatalogueEntriesPage.as_view()),
    urls.re_path("catalogue/entries/(?P<pk>\d+)/(?P<tab>\w+)/", views.CatalogueEntriesView.as_view()),

    # Layer
    urls.path("layer/submission/", views.LayerSubmission.as_view()),     
    urls.re_path("layer/submission/(?P<pk>\d+)/(?P<tab>\w+)/", views.LayerSubmissionView.as_view()),
    urls.path("layer/subscriptions/", views.LayerSubscriptions.as_view()),
    urls.re_path("layer/subscriptions/(?P<pk>\d+)/", views.LayerSubscriptionsView.as_view()),

    # GeoServerQueue
    urls.path("geoserver-queue/", views.GeoServerQueue.as_view()),

    # Layer monitor
    # urls.path("geoserver/", views.GeoServerViewSet.as_view()),

    # CDDPQueue
    urls.path("cddp-queue/", views.CDDPQueueView.as_view()),

    # Usergroups
    urls.path("geoserver-groups/", views.GeoServerGroupsView.as_view()),
    urls.re_path("geoserver-group/(?P<pk>\d+)/", views.GeoServerGroupView.as_view()),
    
    # Geoserver Layer Healthcheck
    urls.path("geoserver-layer-healthcheck/", views.GeoServerLayerHealthcheckView.as_view()),

    urls.path("oldcatalogue/", views.OldCatalogueVue.as_view()),

    # sentry
    urls.path("sentry-debug/", trigger_error),

    # users, groups and roles file
    urls.path('api/geoserver-config-files/', FileListView.as_view(), name='geoserver-config-files'),
    urls.path('api/geoserver-config-files/retrieve-file/', FileDownloadView.as_view(), name='geoserver-retrieve-file'),
    urls.path('api/geoserver-config-files/delete-file/', FileDeleteView.as_view(), name='geoserver-delete-config-file'),

    urls.path('api/logcontents/', views.get_logs, name='get_logs'),
    urls.path('logfile/', views.LogFileView.as_view(), name='logfile'),
    urls.path('api/publish_entries/<int:publish_entry_pk>/purge_cache/', views.PurgeTileCacheAPIView.as_view(), name='purge-publish-entry-cache'),
]

# DBCA Template URLs
urlpatterns.append(urls.path("logout/", auth_views.LogoutView.as_view(), {"next_page": "/"}, name="logout"))
if conf.settings.ENABLE_DJANGO_LOGIN:
    urlpatterns.append(urls.re_path(r"^ssologin/", auth_views.LoginView.as_view(), name="ssologin"))
