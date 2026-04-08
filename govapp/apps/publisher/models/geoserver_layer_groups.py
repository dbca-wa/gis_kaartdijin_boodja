"""Kaartdijin Boodja Publisher GeoServer Layer Group Models."""

# Standard
import logging

# Third-Party
import reversion
from django.db import models
from django.forms import ValidationError

# Local
from govapp.apps.publisher.models.geoserver_pools import GeoServerPool
from govapp.apps.publisher.models.workspaces import Workspace
from govapp.common import mixins


# Logging
log = logging.getLogger(__name__)


@reversion.register()
class GeoServerLayerGroup(mixins.RevisionedMixin):
    """A named group of GeoServer layers published under a single identifier.

    A layer group allows WMS/WFS clients to request multiple layers by a
    single name.  All member channels must belong to the same workspace and
    the same GeoServer pool as the group itself.
    """

    name = models.CharField(
        max_length=255,
        help_text="Name of the layer group as it will appear in GeoServer.",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Human-readable title displayed in WMS capabilities.",
    )
    abstract = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the layer group.",
    )
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="layer_groups",
        help_text="All member layers must belong to this workspace.",
    )
    geoserver_pool = models.ForeignKey(
        GeoServerPool,
        on_delete=models.CASCADE,
        related_name="layer_groups",
        help_text="All member layers must target this GeoServer pool.",
    )
    published_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=(
            "The name under which this group was last published to GeoServer. "
            "Null means the group has never been published. "
            "Differs from 'name' when the user has renamed the group since the "
            "last publish; in that case the old name is deleted from GeoServer "
            "and the new name is created."
        ),
    )
    needs_republish = models.BooleanField(
        default=False,
        help_text=(
            "Set to True automatically when member layers are added or removed "
            "after the last publish. Cleared on successful publish."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """GeoServerLayerGroup Model Metadata."""

        verbose_name = "GeoServer Layer Group"
        verbose_name_plural = "GeoServer Layer Groups"
        unique_together = ("workspace", "name")

    def __str__(self) -> str:
        return f"{self.workspace.name}:{self.name}"


@reversion.register()
class GeoServerLayerGroupEntry(mixins.RevisionedMixin):
    """An ordered membership record linking a publish channel to a layer group.

    Each entry represents one layer (via its GeoServerPublishChannel) that
    belongs to a GeoServerLayerGroup.  The 'order' field controls the
    rendering order in GeoServer (lower = rendered first / bottom of stack).
    """

    layer_group = models.ForeignKey(
        GeoServerLayerGroup,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    publish_channel = models.ForeignKey(
        # String reference to avoid circular import with publish_channels module.
        "publisher.GeoServerPublishChannel",
        on_delete=models.CASCADE,
        related_name="layer_group_entries",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Rendering order within the group (0 = bottom of stack).",
    )

    class Meta:
        """GeoServerLayerGroupEntry Model Metadata."""

        verbose_name = "GeoServer Layer Group Entry"
        verbose_name_plural = "GeoServer Layer Group Entries"
        unique_together = ("layer_group", "publish_channel")
        ordering = ["order"]

    def clean(self) -> None:
        """Validate workspace and GeoServer pool consistency.

        All member channels must share the same workspace and GeoServer pool
        as the parent layer group.  This prevents GeoServer from receiving a
        group whose members span multiple workspaces or pools, which is not
        supported.
        """
        if self.publish_channel_id and self.layer_group_id:
            channel = self.publish_channel
            group = self.layer_group

            if channel.workspace_id != group.workspace_id:
                raise ValidationError(
                    f"Publish channel workspace '{channel.workspace}' does not match "
                    f"layer group workspace '{group.workspace}'."
                )

            if channel.geoserver_pool_id != group.geoserver_pool_id:
                raise ValidationError(
                    f"Publish channel GeoServer pool '{channel.geoserver_pool}' does not match "
                    f"layer group GeoServer pool '{group.geoserver_pool}'."
                )

    def save(self, *args, **kwargs) -> None:
        """Run full_clean before saving to enforce workspace/pool constraints."""
        self.full_clean()
        super().save(*args, **kwargs)
        # Mark the parent group as needing a republish whenever a member is
        # added or updated, but only if the group has already been published.
        if self.layer_group.published_name:
            GeoServerLayerGroup.objects.filter(pk=self.layer_group_id).update(
                needs_republish=True
            )

    def delete(self, *args, **kwargs):
        """Mark parent group as needing republish when a member is removed."""
        layer_group_id = self.layer_group_id
        published_name = self.layer_group.published_name
        result = super().delete(*args, **kwargs)
        if published_name:
            GeoServerLayerGroup.objects.filter(pk=layer_group_id).update(
                needs_republish=True
            )
        return result

    def __str__(self) -> str:
        return f"{self.layer_group} — {self.publish_channel} (order={self.order})"
