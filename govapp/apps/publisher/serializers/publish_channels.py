"""Kaartdijin Boodja Publisher Django Serializers."""


# Third-Party
import pytz
from rest_framework import serializers

# Local
from govapp.apps.publisher import models


class CDDPPublishChannelSerializer(serializers.ModelSerializer):
    """CDDP Publish Channel Model Serializer."""
    def validate_xml_path(self, value):
        if value is None:
            return ""
        return value

    class Meta:
        """CDDP Publish Channel Model Serializer Metadata."""
        model = models.publish_channels.CDDPPublishChannel
        fields = (
            "id",
            "name",
            "published_at",
            "format",
            "mode",
            "frequency",
            "path",
            "xml_path",
            "publish_entry",
        )
        read_only_fields = (
            "id",        
            "published_at",
            "publish_entry",
        )


class CDDPPublishChannelCreateSerializer(serializers.ModelSerializer):
    def validate_xml_path(self, value):
        if value is None:
            return ""
        return value

    class Meta:
        """CDDP Publish Channel Model Create Serializer Metadata."""
        model = CDDPPublishChannelSerializer.Meta.model
        fields = CDDPPublishChannelSerializer.Meta.fields
        # No read only fields on this serializer
        # This allows the `create` action to specify a Publish Entry
        read_only_fields = (
            "id",
            "published_at",
        )


class GeoServerPublishChannelSerializer(serializers.ModelSerializer):
    """GeoServer Publish Channel Model Serializer."""
    workspace_name = serializers.ReadOnlyField(source='workspace.name')
    geoserver_pool_name = serializers.ReadOnlyField(source='geoserver_pool.name')
    layer_name_with_workspace = serializers.ReadOnlyField()
    geoserver_pool_url_ui = serializers.SerializerMethodField()
    store_type_name = serializers.ReadOnlyField(source='get_store_type_display')
    published_at = serializers.SerializerMethodField()
    
    class Meta:
        """GeoServer Publish Channel Model Serializer Metadata."""
        model = models.publish_channels.GeoServerPublishChannel
        fields = "__all__"
        read_only_fields = (
            "id",
            "name",
            "published_at",
            "publish_entry",
            "workspace_name",
            "store_type_name",
            "name",
            "description",
            "geoserver_pool_name",
            "geoserver_pool_url_ui",
        )

    def to_internal_value(self, data):
        # Convert empty strings to None for integer fields
        if data.get('expire_server_cache_after_n_seconds') == "":
            data['expire_server_cache_after_n_seconds'] = None
        if data.get('expire_client_cache_after_n_seconds') == "":
            data['expire_client_cache_after_n_seconds'] = None
        if data.get('gpkg_memory_map_size') == "":
            data['gpkg_memory_map_size'] = None
        return super().to_internal_value(data)

    def get_published_at(self, obj):
        """Convert published_at to the desired format."""
        if obj.published_at:
            # Convert to local time
            local_time = obj.published_at.astimezone(pytz.timezone('Australia/Perth'))
            # Return formatted string
            return local_time.strftime('%d %b %Y %I:%M %p')
        return None

    def get_geoserver_pool_url_ui(self, obj):
        if obj.geoserver_pool:
            if obj.geoserver_pool.url_ui:
                return f'{obj.geoserver_pool.url_ui}'
            else:
                return f'{obj.geoserver_pool.url}'
        return ''
        
    def validate(self, data):
        _validate_bbox(data)
        return data
        

class GeoServerLayerHealthcheckSerializer(serializers.ModelSerializer):
    health_status_str = serializers.ReadOnlyField(source='get_health_status_display')
    geoserver_pool_name = serializers.SerializerMethodField()
    geoserver_pool_url = serializers.SerializerMethodField()
    publish_entry_id = serializers.SerializerMethodField()
    last_check_time_str = serializers.SerializerMethodField()

    class Meta:
        model = models.publish_channels.GeoServerLayerHealthcheck
        fields = [
            'id',
            'geoserver_publish_channel',
            'layer_name',
            'health_status',
            'health_status_str',
            'last_check_time',
            'error_message',
            'geoserver_pool_name',
            'geoserver_pool_url',
            'publish_entry_id',
            'last_check_time_str',
        ]
        datatables_always_serialize = [
            'health_status_str',
            'geoserver_pool_name',
            'geoserver_pool_url',
            'publish_entry_id',
            'last_check_time_str',
        ]

    def get_last_check_time_str(self, obj):
        temp = obj.last_check_time
        return temp.strftime("%d/%m/%Y %I:%M%p")

    def get_publish_entry_id(self, obj):
        if obj.geoserver_publish_channel and obj.geoserver_publish_channel.publish_entry:
            return obj.geoserver_publish_channel.publish_entry.id
        else:
            return ''

    def get_geoserver_pool_name(self, obj):
        if obj.geoserver_publish_channel and obj.geoserver_publish_channel.geoserver_pool:
            return obj.geoserver_publish_channel.geoserver_pool.name
        else:
            return ''

    def get_geoserver_pool_url(self, obj):
        if obj.geoserver_publish_channel and obj.geoserver_publish_channel.geoserver_pool:
            return obj.geoserver_publish_channel.geoserver_pool.url
        else:
            return ''


class GeoServerPublishChannelCreateSerializer(serializers.ModelSerializer):
    """GeoServer Publish Channel Model Create Serializer."""

    class Meta:
        """GeoServer Publish Channel Model Create Serializer Metadata."""
        model = models.publish_channels.GeoServerPublishChannel
        fields = "__all__"
        # No read only fields on this serializer
        # This allows the `create` action to specify a Publish Entry
        read_only_fields = (
            "id",
            "name",
            "published_at",
        )

    def to_internal_value(self, data):
        # Convert empty strings to None for integer fields
        if data.get('expire_server_cache_after_n_seconds') == "":
            data['expire_server_cache_after_n_seconds'] = None
        if data.get('expire_client_cache_after_n_seconds') == "":
            data['expire_client_cache_after_n_seconds'] = None
        if data.get('gpkg_memory_map_size') == "":
            data['gpkg_memory_map_size'] = None
        return super().to_internal_value(data)
    
    def validate(self, data):
        _validate_bbox(data)
        return data

def _validate_bbox(data):
    if 'override_bbox' not in data or data['override_bbox'] == False:
        return
    if _has_null(data['native_crs'], 
                    data['nbb_minx'], data['nbb_maxx'], data['nbb_miny'], data['nbb_maxy'], data['nbb_crs'],
                    data['llb_minx'], data['llb_maxx'], data['llb_miny'], data['llb_maxy'], data['llb_crs']):
        raise serializers.ValidationError("'If override_bbox is True, every related fields must be filled.")
        
def _has_null(*args):
    for arg in args:
        if arg == None:
            return True
    return False


class FTPPublishChannelSerializer(serializers.ModelSerializer):
    """FTP Publish Channel Model Serializer."""
    #workspace_name = serializers.ReadOnlyField(source='workspace.name')
    
    class Meta:
        """FTP Publish Channel Model Serializer Metadata."""
        model = models.publish_channels.FTPPublishChannel
        fields = "__all__"
        read_only_fields = (
            "id",
             "published_at",
        )


class FTPPublishChannelCreateSerializer(serializers.ModelSerializer):
    """FTP Publish Channel Model Create Serializer."""
    class Meta:
        """FTP Publish Channel Model Create Serializer Metadata."""
        model = FTPPublishChannelSerializer.Meta.model
        fields = FTPPublishChannelSerializer.Meta.fields
        # No read only fields on this serializer
        # This allows the `create` action to specify a Publish Entry
        read_only_fields = (
            "id",
            "published_at",
        )


class FTPServerSerializer(serializers.ModelSerializer):
    """FTP Publish Channel Model Serializer."""

    class Meta:
        """CDDP Publish Channel Model Serializer Metadata."""
        model = models.publish_channels.FTPServer
        fields = (
            "id",
            "name",
        )
        read_only_fields = (
            "id",        
            "created"
        )
        
        
class GeoServerQueueSerializer(serializers.ModelSerializer):
    """GeoServer Queue Model Serializer."""
    name = serializers.CharField(source='publish_entry.name')
    status = serializers.SerializerMethodField()
    submitter = serializers.SerializerMethodField()
    queue_type = serializers.SerializerMethodField()

    class Meta:
        """GeoServer Queue Model Serializer Metadata."""
        model = models.geoserver_queues.GeoServerQueue
        fields = "__all__"
        
    def get_status(self, obj):
        # Use different display labels for PURGE_CACHE queue type
        if obj.queue_type == models.geoserver_queues.GeoServerQueueType.PURGE_CACHE:
            status_label_map = {
                models.geoserver_queues.GeoServerQueueStatus.READY: "READY",
                models.geoserver_queues.GeoServerQueueStatus.PROCESSING: "PROCESSING",
                models.geoserver_queues.GeoServerQueueStatus.PUBLISHED: "PURGED",
                models.geoserver_queues.GeoServerQueueStatus.FAILED: "FAILED",
            }
            return status_label_map.get(obj.status, obj.status)
        for status in models.geoserver_queues.GeoServerQueueStatus:
            if status == obj.status:
                return status.name

    def get_queue_type(self, obj):
        for queue_type in models.geoserver_queues.GeoServerQueueType:
            if queue_type == obj.queue_type:
                return queue_type.name
        return None

    def get_submitter(self, obj):
        first_name = obj.submitter.first_name if hasattr(obj.submitter, 'first_name') else ""
        last_name = obj.submitter.last_name if hasattr(obj.submitter, 'last_name') else ""
        return f"{first_name} {last_name}"