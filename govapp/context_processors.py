"""Context processors for the Django project."""


# Third-Party
from django import conf
from django import http
from django.core.cache import cache
from django.db.models import Count

# Typing
from typing import Any

from govapp import settings
from govapp.apps.accounts.utils import user_can_view_logs
from govapp.apps.publisher.models.publish_channels import HealthCheckLevel, get_unhealthy_channels


def variables(request: http.HttpRequest) -> dict[str, Any]:
    """Constructs a context dictionary to be passed to the templates.

    Args:
        request (http.HttpRequest): HTTP request object.

    Returns:
        dict[str, Any]: Context for the templates.
    """
    # Construct and return context  
    is_django_admin = False
    is_admin = False
    is_catalogue_admin = False
    is_able_to_view_logs = False

    if request.session.session_key is not None:
        is_django_admin = cache.get('is_django_admin'+ str(request.session.session_key))
        is_admin = cache.get('is_admin'+ str(request.session.session_key))
        is_catalogue_admin = cache.get('is_catalogue_admin' + str(request.session.session_key))
        is_able_to_view_logs = cache.get('is_able_to_view_logs' + str(request.session.session_key))
        
        if is_django_admin is None:
            is_django_admin = request.user.groups.filter(name="Django Admin").exists()
            cache.set('is_django_admin'+ str(request.session.session_key), is_django_admin,  86400)
        if is_admin is None:
            is_admin = request.user.groups.filter(name=settings.GROUP_ADMINISTRATORS).exists()
            cache.set('is_admin'+ str(request.session.session_key), is_admin,  86400)
        if is_catalogue_admin is None:
            is_catalogue_admin = request.user.groups.filter(name=settings.GROUP_CATALOGUE_ADMIN).exists()
            cache.set('is_catalogue_admin' + str(request.session.session_key), is_catalogue_admin, 3600)
        if is_able_to_view_logs is None:
            is_able_to_view_logs = user_can_view_logs(request.user)
            cache.set('is_able_to_view_logs' + str(request.session.session_key), is_catalogue_admin, 3600)
    
    # Layer Health: the total for the menu badge and the count per level for the health check page,
    # only for the users who see the menu item
    layer_health_unhealthy_count = 0
    layer_health_badge_title = ''
    layer_health_level_badges = []
    if request.user.is_superuser or is_admin:
        # Number of unhealthy layers per health check level, in one query
        level_counts = dict(
            get_unhealthy_channels().order_by().values_list('health_check_level').annotate(n=Count('id', distinct=True))
        )
        layer_health_unhealthy_count = sum(level_counts.values())
        if layer_health_unhealthy_count:
            per_level = ', '.join(f'{level.label} {level_counts.get(level.value, 0)}' for level in HealthCheckLevel)
            layer_text = 'layer' if layer_health_unhealthy_count == 1 else 'layers'
            # e.g. "29 unhealthy layers: Critical 1, Business Hours 0, Non Critical 28"
            layer_health_badge_title = f'{layer_health_unhealthy_count} unhealthy {layer_text}: {per_level}'
        else:
            layer_health_badge_title = 'No unhealthy layers'
        # e.g. Critical 1, Business Hours 0, Non Critical 28
        layer_health_level_badges = [
            {'level': level.value, 'label': level.label, 'count': level_counts.get(level.value, 0)}
            for level in HealthCheckLevel
        ]

    return {
        "template_group": "kaartdijinboodja",
        "template_title": "",
        "app_build_url": conf.settings.DEV_APP_BUILD_URL,
        "GIT_COMMIT_HASH": conf.settings.GIT_COMMIT_HASH,
        "DJANGO_SETTINGS": conf.settings,
        "settings": conf.settings,
        "is_django_admin": is_django_admin, # request.user.groups.filter(name="Django Admin").exists(),
        "is_admin": is_admin, # request.user.groups.filter(name="Administrators").exists(),
        'is_catalogue_admin': is_catalogue_admin,
        'MANAGEMENT_COMMANDS_PAGE_ENABLED': conf.settings.MANAGEMENT_COMMANDS_PAGE_ENABLED,
        'is_able_to_view_logs': is_able_to_view_logs,
        'layer_health_unhealthy_count': layer_health_unhealthy_count,
        'layer_health_badge_title': layer_health_badge_title,
        'layer_health_level_badges': layer_health_level_badges,
    }
