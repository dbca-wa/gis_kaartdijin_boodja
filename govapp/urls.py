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


# Admin Site Settings
admin.site.site_header = conf.settings.PROJECT_TITLE
admin.site.index_title = conf.settings.PROJECT_TITLE
admin.site.site_title = conf.settings.PROJECT_TITLE


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

    # Management Command Endpoints
    urls.path("api/management/", urls.include("govapp.commands")),
    
    # Templates Pages
    urls.re_path("management-commands/", views.ManagementCommandsView.as_view()),
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




    urls.path("oldcatalogue/", views.OldCatalogueVue.as_view()),

]

# DBCA Template URLs
urlpatterns.append(urls.path("logout/", auth_views.LogoutView.as_view(), {"next_page": "/"}, name="logout"))
if conf.settings.ENABLE_DJANGO_LOGIN:
    urlpatterns.append(urls.re_path(r"^ssologin/", auth_views.LoginView.as_view(), name="ssologin"))
