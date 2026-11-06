import logging

from django.core.management.base import BaseCommand, CommandError
from govapp.apps.publisher.models.geoserver_pools import GeoServerPool

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize users, roles, and groups with GeoServer.'

    def handle(self, *args, **options):
        errors = []
        geoservers = GeoServerPool.enabled_targets()
        for geoserver in geoservers:
            # A geoserver that fails must not stop the sync of the other geoservers
            try:
                # Write the users and groups to the GeoServer user file
                geoserver.sync_usergroup_file()

                # Sync relations between users and roles
                failed_usernames = geoserver.sync_user_roles()

                # Sync relations between roles with grous ###
                geoserver.sync_groups_roles()
            except Exception as e:
                log.exception(f'Failed to sync users with the geoserver: [{geoserver}]')
                errors.append(f'{geoserver}: {e}')
                continue

            if failed_usernames:
                errors.append(f'{geoserver}: the roles of {len(failed_usernames)} user(s) failed')

        # Fail the command, so the cron job log records the failure
        if errors:
            raise CommandError('; '.join(errors))
