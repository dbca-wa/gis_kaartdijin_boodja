"""Kaartdijin Boodja Publisher GeoServer Queue Excutor."""

# Standard
import logging
import pathlib

# Third-Party
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django.contrib import auth

# Local
from govapp.apps.publisher.models import geoserver_queues
from govapp.apps.publisher.models import geoserver_roles_groups
from govapp.apps.publisher.models.geoserver_queues import GeoServerQueueStatus, GeoServerQueueType
from govapp.apps.publisher.models import geoserver_pools
from govapp.apps.publisher import geoserver_publisher
from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerGroup, GeoServerRole
from govapp.apps.publisher.models.publish_channels import GeoServerPublishChannel
from govapp.apps.publisher.models.workspaces import Workspace
from govapp.gis import geoserver

# Typing
from typing import TYPE_CHECKING 

if TYPE_CHECKING:
    from govapp.apps.publisher.models.publish_entries import PublishEntry
    
# Shortcuts
UserModel = auth.get_user_model()
# Logging
log = logging.getLogger(__name__)

QUEUE_EXPIRED_MINUTES = 1

class GeoServerQueueExcutor:
    def __init__(self) -> None:
        self.result_status = GeoServerQueueStatus.PUBLISHED
        self.result_success = True
        self.publishing_log = ""

    def auto_enqueue(self) -> None:
        """Automatically identify and enqueue eligible publish entries to GeoServer Queue.
        
        This method finds publish entries that meet the following criteria and adds them to the queue:
        1. The entry is registered as a ForeignKey in a GeoServerPublishChannel
        2. The GeoServerPublishChannel.active is True
        3. The GeoServerPublishChannel.geoserver_pool exists and is enabled (geoserver_pool.enabled == True)
        """
        from govapp.apps.publisher.models.publish_entries import PublishEntry
        from govapp.apps.publisher.models.publish_channels import GeoServerPublishChannel
        
        log.info("Starting automatic enqueue process")
        
        # Get all active GeoServerPublishChannels with enabled geoserver_pools
        active_channels = GeoServerPublishChannel.objects.filter(
            active=True,
            geoserver_pool__isnull=False,
            geoserver_pool__enabled=True
        ).select_related('publish_entry', 'geoserver_pool')
        
        # Get unique publish entries from these channels
        eligible_entries_ids = active_channels.values_list('publish_entry_id', flat=True).distinct()
        eligible_entries = PublishEntry.objects.filter(id__in=eligible_entries_ids)
        
        count = 0
        for entry in eligible_entries:
            # Check if there's already a queue item for this entry that's not completed
            already_queued = geoserver_queues.GeoServerQueue.is_publish_entry_queued(
                entry, queue_type=GeoServerQueueType.PUBLISH
            )

            if not already_queued:
                # Create new queue item
                geoserver_queues.GeoServerQueue.objects.create(
                    publish_entry=entry,
                    queue_type=GeoServerQueueType.PUBLISH,
                    symbology_only=False,  # Full publish by default
                )
                count += 1
                log.info(f"{count}: Auto-enqueued publish entry: [{entry}]")
        
        log.info(f"Auto-enqueue process completed. Added {count} entries to queue")

    def excute(self) -> None:
        queue_items = self._retrieve_target_items()
        log.info(f"Start publishing for {queue_items.count()} geoserver queue items.")

        for queue_item in queue_items:
            try:
                self._init_excuting(queue_item=queue_item)

                if queue_item.queue_type == GeoServerQueueType.PURGE_CACHE:
                    self._purge_cache_for_queue_item(queue_item)
                else:
                    if queue_item.symbology_only:
                        # Symbology-only: publish style directly to GeoServer, no file transfer needed
                        for geoserver_publish_channel in queue_item.publish_entry.geoserver_channels.all():
                            geoserver_pool = geoserver_publish_channel.geoserver_pool
                            if not geoserver_pool:
                                self.result_status = GeoServerQueueStatus.FAILED
                                self.result_success = False
                                self._add_publishing_log(f"[{queue_item.publish_entry.name}] Publishing failed.  No geoserver_pool configured.")
                                continue
                            if not geoserver_pool.enabled:
                                self.result_status = GeoServerQueueStatus.FAILED
                                self.result_success = False
                                self._add_publishing_log(f"[{queue_item.publish_entry.name} - {geoserver_pool.url}] Publishing failed.  Geoserver_pool is not enabled.")
                                continue
                            workspaces_in_kb = Workspace.objects.all()
                            for workspace in workspaces_in_kb:
                                geoserver_pool.create_workspace_if_not_exists(workspace.name)
                            self._publish_to_a_geoserver(geoserver_publish_channel)
                    else:
                        # Phase 1: convert file only; kb_geoserver_manager will transfer it to the shared volume
                        self.result_status = GeoServerQueueStatus.CONVERTED
                        self._convert_publish_queue_item(queue_item)

                self._update_result(queue_item=queue_item)

            except Exception as e:
                log.error(f"Unexpected error while processing queue item pk={queue_item.pk}: {e}", exc_info=True)
                self.result_status = GeoServerQueueStatus.FAILED
                self.result_success = False
                self._add_publishing_log(f"Unexpected error: {e}")
                try:
                    self._update_result(queue_item=queue_item)
                except Exception as save_error:
                    log.error(f"Failed to save error state for queue item pk={queue_item.pk}: {save_error}", exc_info=True)

    def _retrieve_target_items(self):
        """ Retrieve items that their status is ready or status is processing & started before 30 minutes from now """
        query = Q(status=GeoServerQueueStatus.READY) | \
                Q(status=GeoServerQueueStatus.PROCESSING, started_at__lte=timezone.now() - timezone.timedelta(minutes=QUEUE_EXPIRED_MINUTES))
        target_items = geoserver_queues.GeoServerQueue.objects.filter(query).order_by('created_at')
        return target_items
    
    def _init_excuting(self, queue_item):
        queue_item.change_status(GeoServerQueueStatus.PROCESSING)
        self.publishing_log = queue_item.publishing_result if queue_item.publishing_result is not None else ""
        self.result_status = GeoServerQueueStatus.PUBLISHED
        self.result_success = True
        self._add_publishing_log("Start publishing..")

    def _add_publishing_log(self, msg):
        log.info(msg)
        log_msg = f"[{timezone.now()}] {msg}\n"
        # log.info(log_msg)
        self.publishing_log += log_msg
        return log_msg
    
    def _publish_to_a_geoserver(self, geoserver_publish_channel: GeoServerPublishChannel):
        # Publish here
        res, exc = geoserver_publisher.publish(geoserver_publish_channel)
        
        if res:
            self._add_publishing_log(f"[{geoserver_publish_channel.publish_entry.name} - {geoserver_publish_channel.geoserver_pool.url}] Publishing succeed.")
            
        else :
            self.result_status = GeoServerQueueStatus.FAILED
            self.result_success = False
            self._add_publishing_log(f"[{geoserver_publish_channel.publish_entry.name} - {geoserver_publish_channel.geoserver_pool.url}] Publishing failed.")
            self._add_publishing_log(f"[{geoserver_publish_channel.publish_entry.name} - {geoserver_publish_channel.geoserver_pool.url}] {exc}")

    def _purge_cache_for_queue_item(self, queue_item: geoserver_queues.GeoServerQueue) -> None:
        """Send a GWC masstruncate request to every active GeoServer channel for the publish entry."""
        publish_entry = queue_item.publish_entry
        layer_name = publish_entry.catalogue_entry.name

        active_channels = GeoServerPublishChannel.objects.filter(
            publish_entry=publish_entry,
            active=True,
        ).select_related('geoserver_pool', 'workspace')

        if not active_channels.exists():
            self.result_status = GeoServerQueueStatus.FAILED
            self.result_success = False
            self._add_publishing_log(f"[{layer_name}] Purge cache failed. No active GeoServer publish channels found.")
            return

        for channel in active_channels:
            geoserver_pool = channel.geoserver_pool

            if not geoserver_pool:
                self.result_status = GeoServerQueueStatus.FAILED
                self.result_success = False
                self._add_publishing_log(f"[{layer_name}] Purge cache failed. Channel pk={channel.pk} has no geoserver_pool.")
                continue

            if not geoserver_pool.enabled:
                self._add_publishing_log(f"[{layer_name} - {geoserver_pool.name}] Skipped purge. GeoServer pool is disabled.")
                continue

            workspace_name = channel.workspace.name
            full_layer_name = f"{workspace_name}:{layer_name}"

            # Use cluster nodes if available, otherwise fall back to the pool's own URL.
            cluster_nodes = geoserver_pool.cluster_nodes.filter(enabled=True)
            if cluster_nodes.exists():
                targets = [
                    (node.server_url, node.username, node.password, f"{geoserver_pool.name} / node {node.server_url}")
                    for node in cluster_nodes
                ]
            else:
                targets = [
                    (geoserver_pool.url, geoserver_pool.username, geoserver_pool.password, geoserver_pool.name)
                ]

            for target_url, target_username, target_password, target_label in targets:
                url = f"{target_url}/gwc/rest/masstruncate"
                try:
                    response = requests.post(
                        url=url,
                        auth=HTTPBasicAuth(target_username, target_password),
                        headers={'Content-type': 'text/xml'},
                        data=f"<truncateLayer><layerName>{full_layer_name}</layerName></truncateLayer>",
                        timeout=30,
                    )
                    if response.status_code == 200:
                        self._add_publishing_log(f"[{full_layer_name} - {target_label}] Purge cache succeeded.")
                    else:
                        self.result_status = GeoServerQueueStatus.FAILED
                        self.result_success = False
                        self._add_publishing_log(
                            f"[{full_layer_name} - {target_label}] Purge cache failed. "
                            f"Status: {response.status_code}, Response: {response.text}"
                        )
                except requests.exceptions.RequestException as e:
                    self.result_status = GeoServerQueueStatus.FAILED
                    self.result_success = False
                    self._add_publishing_log(f"[{full_layer_name} - {target_label}] Purge cache failed. Network error: {e}")

    def _convert_publish_queue_item(self, queue_item: geoserver_queues.GeoServerQueue) -> None:
        """Phase 1: Convert the source file for transfer to the shared volume.

        Uses the first active GeoServerPublishChannel to determine the target file format.
        Stores the resulting file path in queue_item.converted_file_path.
        On success the caller sets status → CONVERTED; on failure status → FAILED.
        """
        channels = queue_item.publish_entry.geoserver_channels.filter(active=True)
        if not channels.exists():
            channels = queue_item.publish_entry.geoserver_channels.all()

        if not channels.exists():
            self.result_status = GeoServerQueueStatus.FAILED
            self.result_success = False
            self._add_publishing_log(
                f"[{queue_item.publish_entry.name}] Conversion failed: no GeoServerPublishChannel found."
            )
            return

        # All channels share the same source file; use the first to determine the conversion type.
        channel = channels.first()
        try:
            converted_path = channel.convert_layer()
            queue_item.converted_file_path = str(converted_path)
            queue_item.save(update_fields=['converted_file_path'])
            self._add_publishing_log(
                f"[{queue_item.publish_entry.name}] File converted successfully: {converted_path}"
            )
        except Exception as e:
            self.result_status = GeoServerQueueStatus.FAILED
            self.result_success = False
            self._add_publishing_log(f"[{queue_item.publish_entry.name}] Conversion failed: {e}")
            log.error(f"Conversion failed for queue item pk={queue_item.pk}: {e}", exc_info=True)

    def excute_ready_to_publish(self) -> None:
        """Phase 2: Configure GeoServer for READY_TO_PUBLISH items.

        Picks up items that kb_geoserver_manager has placed on the shared volume
        and configures the GeoServer datastore/layer using the file path on the volume.
        """
        queue_items = self._retrieve_ready_to_publish_items()
        log.info(f"Start GeoServer configuration for {queue_items.count()} items.")

        for queue_item in queue_items:
            try:
                self.publishing_log = queue_item.publishing_result or ""
                self.result_status = GeoServerQueueStatus.PUBLISHED
                self.result_success = True
                self._add_publishing_log("Starting GeoServer configuration from shared volume...")

                self._configure_geoserver_for_queue_item(queue_item)
                self._update_result(queue_item=queue_item)

            except Exception as e:
                log.error(
                    f"Unexpected error while configuring GeoServer for queue item pk={queue_item.pk}: {e}",
                    exc_info=True
                )
                self.result_status = GeoServerQueueStatus.PUBLISH_FAILED
                self.result_success = False
                self._add_publishing_log(f"Unexpected error: {e}")
                try:
                    self._update_result(queue_item=queue_item)
                except Exception as save_error:
                    log.error(
                        f"Failed to save error state for queue item pk={queue_item.pk}: {save_error}",
                        exc_info=True
                    )

    def _retrieve_ready_to_publish_items(self):
        """Retrieve all READY_TO_PUBLISH PUBLISH queue items."""
        return geoserver_queues.GeoServerQueue.objects.filter(
            status=GeoServerQueueStatus.READY_TO_PUBLISH,
            queue_type=GeoServerQueueType.PUBLISH
        ).order_by('created_at')

    def _configure_geoserver_for_queue_item(self, queue_item: geoserver_queues.GeoServerQueue) -> None:
        """Configure GeoServer using the file placed on the shared volume by kb_geoserver_manager.

        For each active GeoServerPublishChannel of the publish entry, calls the appropriate
        path-based GeoServer configuration method (configure_geopackage_from_path or
        configure_geotiff_from_path) then publishes symbology and sets the default style.
        """
        from govapp.apps.publisher.models.publish_channels import StoreType

        if not queue_item.converted_file_path:
            self.result_status = GeoServerQueueStatus.PUBLISH_FAILED
            self.result_success = False
            self._add_publishing_log(
                f"[{queue_item.publish_entry.name}] GeoServer configuration failed: "
                f"no converted_file_path on queue item."
            )
            return

        # The filename on the shared volume matches the basename of the converted file.
        # kb_geoserver_manager places the file at: <VOLUME_PATH>/<workspace>/<name>/<filename>
        filename = pathlib.Path(queue_item.converted_file_path).name

        channels = queue_item.publish_entry.geoserver_channels.filter(active=True)
        if not channels.exists():
            channels = queue_item.publish_entry.geoserver_channels.all()

        if not channels.exists():
            self.result_status = GeoServerQueueStatus.PUBLISH_FAILED
            self.result_success = False
            self._add_publishing_log(
                f"[{queue_item.publish_entry.name}] GeoServer configuration failed: "
                f"no GeoServerPublishChannel found."
            )
            return

        publish_succeeded_for_any = False

        for channel in channels:
            pool = channel.geoserver_pool
            if not pool:
                self.result_status = GeoServerQueueStatus.PUBLISH_FAILED
                self.result_success = False
                self._add_publishing_log(
                    f"[{queue_item.publish_entry.name}] Skipped channel pk={channel.pk}: no geoserver_pool."
                )
                continue
            if not pool.enabled:
                self._add_publishing_log(
                    f"[{queue_item.publish_entry.name} - {pool.name}] Skipped: GeoServer pool is disabled."
                )
                continue

            geoserver_obj = geoserver.geoserverWithCustomCreds(
                pool.url, pool.username, pool.password
            )
            workspace_name = channel.workspace.name
            layer_name = queue_item.publish_entry.catalogue_entry.metadata.name

            # kb_geoserver_manager places files at: <VOLUME_PATH>/<workspace>/<name>/<filename>
            volume_file_path = (
                pathlib.Path(settings.GEOSERVER_VOLUME_PATH)
                / workspace_name
                / queue_item.publish_entry.name
                / filename
            )

            try:
                if channel.store_type == StoreType.GEOPACKAGE:
                    geoserver_obj.configure_geopackage_from_path(
                        workspace=workspace_name,
                        layer=layer_name,
                        file_path_on_volume=volume_file_path,
                        memory_map_size=channel.gpkg_memory_map_size,
                    )
                elif channel.store_type == StoreType.GEOTIFF:
                    geoserver_obj.configure_geotiff_from_path(
                        workspace=workspace_name,
                        layer=layer_name,
                        file_path_on_volume=volume_file_path,
                    )
                else:
                    self.result_status = GeoServerQueueStatus.PUBLISH_FAILED
                    self.result_success = False
                    self._add_publishing_log(
                        f"[{queue_item.publish_entry.name} - {pool.url}] Unknown store_type: {channel.store_type}."
                    )
                    continue

                # Publish style
                channel.publish_geoserver_symbology(geoserver=geoserver_obj)

                # Set default style
                style_name = (
                    queue_item.publish_entry.catalogue_entry.symbology.name
                    if hasattr(queue_item.publish_entry.catalogue_entry, 'symbology')
                    and queue_item.publish_entry.catalogue_entry.symbology.name
                    and queue_item.publish_entry.catalogue_entry.symbology.sld
                    else 'generic'
                )
                geoserver_obj.set_default_style_to_layer(
                    style_name=style_name,
                    workspace_name=workspace_name,
                    layer_name=layer_name,
                )

                publish_time = timezone.now()
                channel.published_at = publish_time
                channel.save(update_fields=['published_at'])
                publish_succeeded_for_any = True

                self._add_publishing_log(
                    f"[{queue_item.publish_entry.name} - {pool.url}] GeoServer configuration succeeded."
                )

            except Exception as e:
                self.result_status = GeoServerQueueStatus.PUBLISH_FAILED
                self.result_success = False
                self._add_publishing_log(
                    f"[{queue_item.publish_entry.name} - {pool.url}] GeoServer configuration failed: {e}"
                )
                log.error(
                    f"GeoServer configuration failed for channel pk={channel.pk}: {e}",
                    exc_info=True
                )

        if publish_succeeded_for_any:
            queue_item.publish_entry.published_at = timezone.now()
            queue_item.publish_entry.save(update_fields=['published_at'])

    def _update_result(self, queue_item: geoserver_queues.GeoServerQueue):
        queue_item.status = self.result_status
        queue_item.success = self.result_success
        queue_item.publishing_result = self.publishing_log
        queue_item.save()
    
def push(publish_entry: "PublishEntry", symbology_only: bool, submitter: UserModel=None) -> bool:
    if not hasattr(publish_entry, "geoserver_channels"):
        log.info(f"'{publish_entry}' has no GeoServer Publish Channel")
        return False

    already_queued = geoserver_queues.GeoServerQueue.is_publish_entry_queued(
        publish_entry, queue_type=GeoServerQueueType.PUBLISH
    )

    if not already_queued:
        geoserver_queues.GeoServerQueue.objects.create(
            publish_entry=publish_entry,
            queue_type=GeoServerQueueType.PUBLISH,
            symbology_only=symbology_only,
            submitter=submitter)
    return True


def push_purge_cache(publish_entry: "PublishEntry", submitter: UserModel=None) -> bool:
    """Enqueue a purge tile cache job for the given publish entry."""
    already_queued = geoserver_queues.GeoServerQueue.is_publish_entry_queued(
        publish_entry, queue_type=GeoServerQueueType.PURGE_CACHE
    )

    if already_queued:
        log.info(f"'{publish_entry}' purge cache is already queued. Skipping.")
        return False

    geoserver_queues.GeoServerQueue.objects.create(
        publish_entry=publish_entry,
        queue_type=GeoServerQueueType.PURGE_CACHE,
        symbology_only=False,
        submitter=submitter,
    )
    log.info(f"'{publish_entry}' purge cache enqueued.")
    return True


class GeoServerSyncExcutor:
    def sync_geoserver_roles(self):
        log.info(f"Sync geoserver roles...")
        
        # List of the active role names in the KB
        geoserver_role_names = GeoServerRole.objects.filter(active=True).values_list('name', flat=True)
        log.info(f'Roles in KB: [{geoserver_role_names}]')

        # List of the active geoservers in the KB
        geoserver_pool = geoserver_pools.GeoServerPool.objects.filter(enabled=True)

        for geoserver_info in geoserver_pool:  # Perform per geoserver
            geoserver_info.synchronize_roles(geoserver_role_names)

    def sync_geoserver_groups(self):
        log.info(f"Sync geoserver groups...")
        
        # List of the active group names in the KB
        geoserver_group_names = GeoServerGroup.objects.filter(active=True).values_list('name', flat=True)
        log.info(f'Groups in KB: [{geoserver_group_names}]')

        # List of the active geoservers in the KB
        geoserver_pool = geoserver_pools.GeoServerPool.objects.filter(enabled=True)

        for geoserver_info in geoserver_pool:  # Perform per geoserver
            geoserver_info.synchronize_groups(geoserver_group_names)

    def sync_geoserver_role_permissions(self):
        log.info(f"Sync geoserver rules...")

        # List of the active geoservers in the KB
        geoserver_pool = geoserver_pools.GeoServerPool.objects.filter(enabled=True)
        new_rules = geoserver_roles_groups.GeoServerRolePermission.get_rules()
        workspaces_in_kb = set(list(Workspace.objects.all().values_list('name', flat=True)))

        for geoserver_info in geoserver_pool:  # Perform per geoserver
            # Generate GeoServer obj
            # geoserver_obj = geoserver.geoserverWithCustomCreds(geoserver_info.url, geoserver_info.username, geoserver_info.password)
            
            # Make sure all the workspace exist in the geoserver
            for workspace in workspaces_in_kb:
                geoserver_info.create_workspace_if_not_exists(workspace)
            geoserver_info.synchronize_rules(new_rules)

            workspaces_in_geoserver = geoserver_info.get_all_workspaces()
            workspaces_in_geoserver = set([workspace['name'] for workspace in workspaces_in_geoserver])
            log.info(f'Workspaces: [{workspaces_in_geoserver}] exist in the geoserver: [{geoserver_info}].')

            workspaces_to_be_deleted = workspaces_in_geoserver - workspaces_in_kb
            for workspace_to_be_deleted in workspaces_to_be_deleted:
                geoserver_info.delete_workspace(workspace_to_be_deleted)


    def sync_deleted_layers(self):
        log.info(f"Remove all layers on Geoservers that have been removed from KB...")
        
        geoserver_pool = geoserver_pools.GeoServerPool.objects.filter(enabled=True)
        for geoserver_info in geoserver_pool:
            geoserver_obj = geoserver.geoserverWithCustomCreds(geoserver_info.url, geoserver_info.username, geoserver_info.password)
            
            # Retrive layer names from geoserver
            layers = geoserver_obj.get_layers()
            layer_names = [layer['name'].split(':')[1] for layer in layers]

            log.info(f'Layers on the geoserver: [{geoserver_info.url}: [{layer_names}]]')
            
            # Retrive layer names from DB for this geoserver
            name_list = GeoServerPublishChannel.objects.filter(
                geoserver_pool=geoserver_info,
                active=True,  # We want to delete the layers with an "active" value of False from GeoServer.
                publish_entry__catalogue_entry__name__in=[layer_name for layer_name in layer_names]
            ).values_list('publish_entry__catalogue_entry__name', flat=True)
            synced_layer_names_set = set(name_list)

            log.info(f'Layers on the KB: [{synced_layer_names_set}] for the geoserver: [{geoserver_info.url}]')
            
            # Compare layer names
            purge_list = [layer_name for layer_name in layer_names if layer_name not in synced_layer_names_set]

            log.info(f'Layers to be deleted: [{purge_list}] from the geoserver: [{geoserver_info.url}]')
            
            # Call a remove layer api
            for layer_name in purge_list:
                geoserver_obj.delete_layer(layer_name)
