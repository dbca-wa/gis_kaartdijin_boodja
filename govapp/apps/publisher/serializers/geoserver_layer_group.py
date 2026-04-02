"""Kaartdijin Boodja Publisher GeoServer Layer Group Serializers."""

# Third-Party
import pytz
from rest_framework import serializers

# Local
from govapp.apps.publisher.models.geoserver_layer_groups import (
    GeoServerLayerGroup,
    GeoServerLayerGroupEntry,
)


class GeoServerLayerGroupEntrySerializer(serializers.ModelSerializer):
    """Serializer for a single layer group member entry."""

    publish_channel_name = serializers.CharField(
        source="publish_channel.name",
        read_only=True,
    )

    class Meta:
        model = GeoServerLayerGroupEntry
        fields = (
            "id",
            "layer_group",
            "publish_channel",
            "publish_channel_name",
            "order",
        )


class GeoServerLayerGroupSerializer(serializers.ModelSerializer):
    """Serializer for GeoServerLayerGroup with nested member entries."""

    entries = GeoServerLayerGroupEntrySerializer(many=True, read_only=True)
    workspace_name = serializers.CharField(source="workspace.name", read_only=True)
    geoserver_pool_name = serializers.CharField(source="geoserver_pool.name", read_only=True)
    created_at = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    class Meta:
        model = GeoServerLayerGroup
        fields = (
            "id",
            "name",
            "title",
            "abstract",
            "workspace",
            "workspace_name",
            "geoserver_pool",
            "geoserver_pool_name",
            "published_name",
            "needs_republish",
            "entries",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("published_name", "needs_republish")

    def get_created_at(self, obj):
        if obj.created_at:
            local_time = obj.created_at.astimezone(pytz.timezone("Australia/Perth"))
            return local_time.strftime("%d %b %Y %I:%M %p")
        return None

    def get_updated_at(self, obj):
        if obj.updated_at:
            local_time = obj.updated_at.astimezone(pytz.timezone("Australia/Perth"))
            return local_time.strftime("%d %b %Y %I:%M %p")
        return None
