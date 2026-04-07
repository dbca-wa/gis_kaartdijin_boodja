"""Kaartdijin Boodja Publisher GeoServer Layer Group Publisher."""

# Standard
import logging

# Local
from govapp.gis import geoserver as geoserver_utils
from govapp.apps.publisher.models.geoserver_layer_groups import GeoServerLayerGroup

# Logging
log = logging.getLogger(__name__)


def publish(layer_group: GeoServerLayerGroup) -> tuple[bool, Exception | None]:
    """Publish a layer group to GeoServer.

    If the group's current name differs from its previously published name
    (i.e. it was renamed), the old name is deleted from GeoServer first.

    The group is created when it has never been published before, or updated
    when it already exists under the same name.

    Args:
        layer_group (GeoServerLayerGroup): The layer group to publish.

    Returns:
        tuple[bool, Exception | None]: (True, None) on success, or
            (False, exc) on failure.
    """
    try:
        gs = geoserver_utils.geoserverWithCustomCreds(
            layer_group.geoserver_pool.url,
            layer_group.geoserver_pool.username,
            layer_group.geoserver_pool.password,
        )

        workspace = layer_group.workspace.name
        current_name = layer_group.name
        published_name = layer_group.published_name

        # If the group was previously published under a different name, delete
        # the old name from GeoServer before creating under the new name.
        if published_name and published_name != current_name:
            log.info(
                f"Layer group renamed from '{published_name}' to '{current_name}' — "
                f"deleting old entry from GeoServer."
            )
            existing_old = gs.get_layer_group(workspace, published_name)
            if existing_old is not None:
                gs.delete_layer_group(workspace, published_name)

        # Collect ordered layer names ("workspace:layername") from member channels.
        layer_names = [
            entry.publish_channel.layer_name_with_workspace
            for entry in layer_group.entries.select_related("publish_channel__workspace").all()
        ]

        if not layer_names:
            log.warning(
                f"Layer group '{layer_group}' has no member layers — nothing to publish."
            )
            return True, None

        # Verify that every member layer is already published to GeoServer.
        # GeoServer silently discards unknown layers and then rejects the group
        # with "Layer group must not be empty", so we catch this here first.
        missing = []
        for ln in layer_names:
            try:
                details = gs.get_layer_details(ln)
                if details is None:
                    missing.append(ln)
            except Exception:
                # Any error (including 404) means the layer is not available.
                missing.append(ln)
        if missing:
            layer_list = "".join(f"\n• {ln}" for ln in missing)
            msg = (
                f"The following member layers are not yet published to GeoServer "
                f"and must be published individually before the layer group can be "
                f"created:{layer_list}"
            )
            log.error(f"Cannot publish layer group '{layer_group}': {msg}")
            return False, ValueError(msg)

        # Determine whether to POST (create) or PUT (update).
        existing = gs.get_layer_group(workspace, current_name)
        if existing is None:
            log.info(f"Creating layer group '{workspace}:{current_name}' in GeoServer.")
            gs.create_layer_group(
                workspace=workspace,
                name=current_name,
                layer_names=layer_names,
                title=layer_group.title,
                abstract=layer_group.abstract,
            )
        else:
            log.info(f"Updating layer group '{workspace}:{current_name}' in GeoServer.")
            gs.update_layer_group(
                workspace=workspace,
                name=current_name,
                layer_names=layer_names,
                title=layer_group.title,
                abstract=layer_group.abstract,
            )

        # Record the name under which the group is now published and clear the
        # republish flag since the group is now in sync with GeoServer.
        GeoServerLayerGroup.objects.filter(pk=layer_group.pk).update(
            published_name=current_name,
            needs_republish=False,
        )
        log.info(f"Layer group '{layer_group}' published successfully.")

    except Exception as exc:
        log.error(f"Failed to publish layer group '{layer_group}': {exc}")
        return False, exc

    return True, None


def delete_from_geoserver(layer_group: GeoServerLayerGroup) -> tuple[bool, Exception | None]:
    """Remove a layer group from GeoServer and clear its published name.

    Both the current name and, if different, the previously published name
    are deleted from GeoServer so that no stale entries remain.

    Args:
        layer_group (GeoServerLayerGroup): The layer group to remove.

    Returns:
        tuple[bool, Exception | None]: (True, None) on success, or
            (False, exc) on failure.
    """
    try:
        gs = geoserver_utils.geoserverWithCustomCreds(
            layer_group.geoserver_pool.url,
            layer_group.geoserver_pool.username,
            layer_group.geoserver_pool.password,
        )

        workspace = layer_group.workspace.name
        names_to_delete = {layer_group.name}
        if layer_group.published_name:
            names_to_delete.add(layer_group.published_name)

        for name in names_to_delete:
            existing = gs.get_layer_group(workspace, name)
            if existing is not None:
                log.info(f"Deleting layer group '{workspace}:{name}' from GeoServer.")
                gs.delete_layer_group(workspace, name)
            else:
                log.info(
                    f"Layer group '{workspace}:{name}' not found in GeoServer — skipping delete."
                )

        # Clear the published name so the model reflects the unpublished state.
        GeoServerLayerGroup.objects.filter(pk=layer_group.pk).update(
            published_name=None
        )
        log.info(f"Layer group '{layer_group}' removed from GeoServer.")

    except Exception as exc:
        log.error(f"Failed to delete layer group '{layer_group}' from GeoServer: {exc}")
        return False, exc

    return True, None
