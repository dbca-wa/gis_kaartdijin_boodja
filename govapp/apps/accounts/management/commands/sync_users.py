import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from govapp.apps.publisher.models.geoserver_pools import GeoServerPool, GeoServerUserSyncState

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize users, roles, and groups with GeoServer.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Sync every GeoServer even when the KB data has not changed since its last successful sync.',
        )

    def handle(self, *args, **options):
        errors = []
        data_hash = GeoServerPool.build_user_sync_hash()
        geoservers = GeoServerPool.enabled_targets()
        for geoserver in geoservers:
            state = GeoServerUserSyncState.objects.filter(geoserver_pool_id=geoserver.id, cluster_name=geoserver.cluster_name).first()
            if not options['force'] and state and state.data_hash == data_hash:
                log.info(f'Users of the geoserver: [{geoserver}] are up to date (no change in KB since {state.synced_at}).')
                continue

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
                continue

            # Store the hash only after a full success, so a failed geoserver is tried again next time
            GeoServerUserSyncState.objects.update_or_create(
                geoserver_pool_id=geoserver.id,
                cluster_name=geoserver.cluster_name,
                defaults={'data_hash': data_hash, 'synced_at': timezone.now()},
            )

        # Fail the command, so the cron job log records the failure
        if errors:
            raise CommandError('; '.join(errors))
