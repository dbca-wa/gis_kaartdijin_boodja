from django.core.management.base import BaseCommand, CommandError
from govapp.apps.publisher.models.geoserver_pools import GeoServerPool


class Command(BaseCommand):
    help = 'Synchronize users, roles, and groups with GeoServer.'

    def handle(self, *args, **options):
        errors = []
        geoservers = GeoServerPool.enabled_targets()
        for geoserver in geoservers:
            # Write the users and groups to the GeoServer user file
            geoserver.sync_usergroup_file()

            # Sync relations between users and roles
            failed_user_ids = geoserver.sync_user_roles()

            # Sync relations between roles with grous ###
            geoserver.sync_groups_roles()

            if failed_user_ids:
                errors.append(f'{geoserver}: {len(failed_user_ids)} user(s) failed')

        # Fail the command, so the cron job log records the failure
        if errors:
            raise CommandError('; '.join(errors))
