"""Kaartdijin Boodja Publisher Django Serializers."""


# Third-Party
from rest_framework import serializers

# Local
from govapp.apps.publisher import models
from govapp.apps.accounts import serializers as accounts_serializers
from govapp.apps.publisher.models.publish_channels import GeoServerPublishChannel

class PublishEntrySerializer(serializers.ModelSerializer):
    """Publish Entry Model Serializer.""" 
    #accounts_serializers.UserModel
    first_name = serializers.ReadOnlyField(source='assigned_to.first_name')
    last_name = serializers.ReadOnlyField(source='assigned_to.last_name')
    email = serializers.ReadOnlyField(source='assigned_to.email',)
    name = serializers.ReadOnlyField(source='catalogue_entry.name',)
    custodian_name = serializers.ReadOnlyField(source='catalogue_entry.custodian.name',)
    catalogue_type = serializers.ReadOnlyField(source='catalogue_entry.type',)
    publishable_to_ftp = serializers.SerializerMethodField()
    publishable_to_geoserver = serializers.SerializerMethodField()
    publishable_to_cddp = serializers.SerializerMethodField()
    num_of_ftp_publish_channels = serializers.SerializerMethodField()
    num_of_geoserver_publish_channels_active = serializers.SerializerMethodField()
    num_of_geoserver_publish_channels_inactive = serializers.SerializerMethodField()
    num_of_cddp_publish_channels = serializers.SerializerMethodField()
    num_of_cache_enabled_channels = serializers.SerializerMethodField()

    class Meta:
        """Publish Entry Model Serializer Metadata."""
        model = models.publish_entries.PublishEntry
        fields = "__all__"

        read_only_fields = (
            "id",
            "name",
            "status",
            "updated_at",
            "published_at",
            "editors",
            "assigned_to",
            "cddp_channels",
            "geoserver_channels",
            "first_name",
            "last_name",
            "email",
            "custodian_name",
            "catalogue_type"
            "publishable_to_ftp",
            "publishable_to_geoserver",
            "publishable_to_cddp",
            "num_of_ftp_publish_channels",
            "num_of_geoserver_publish_channels_active",
            "num_of_geoserver_publish_channels_inactive",
            "num_of_cddp_publish_channels",
            "num_of_cache_enabled_channels",
        )

    def get_num_of_cache_enabled_channels(self, obj):
        return obj.num_of_cache_enabled_channels

    def get_email(self, obj):
        return obj.email

    def get_publishable_to_ftp(self, obj):
        return obj.publishable_to_ftp

    def get_publishable_to_geoserver(self, obj):
        return obj.publishable_to_geoserver

    def get_publishable_to_cddp(self, obj):
        return obj.publishable_to_cddp

    def get_num_of_ftp_publish_channels(self, obj):
        return obj.num_of_ftp_publish_channels

    def get_num_of_geoserver_publish_channels_active(self, obj):
        return obj.num_of_geoserver_publish_channels_active

    def get_num_of_geoserver_publish_channels_inactive(self, obj):
        return obj.num_of_geoserver_publish_channels_inactive
        
    def get_num_of_cddp_publish_channels(self, obj):
        return obj.num_of_cddp_publish_channels


class PublishEntryCreateSerializer(serializers.ModelSerializer):
    """Publish Entry Model Create Serializer."""
    class Meta:
        """Publish Entry Model Create Serializer Metadata."""
        model = PublishEntrySerializer.Meta.model
        fields = PublishEntrySerializer.Meta.fields
        # No read only fields on this serializer
        # This allows the `create` action to specify a Catalogue Entry
        read_only_fields = (
            "id",
            "name",
            "status",
            "updated_at",
            "published_at",
            "editors",
            "assigned_to",
            "cddp_channels",
            "geoserver_channels",
        )


class PublishEntryCreateEditorSerializer(serializers.Serializer):
    """Publish Entry Model Serializer.""" 
    user_id = serializers.IntegerField()

    class Meta:
        """Publish Entry Model Serializer Metadata."""
        #model = models.publish_entries.PublishEntry
        fields = ('user_id',)


# class PublishEntryListEditorSerializer(serializers.ModelSerializer):
#     """Publish Entry Model Serializer.""" 
#     #accounts_serializers.UserModel
#     #editors_id = serializers.ReadOnlyField(source='editors.id')
#     #last_name = serializers.ReadOnlyField(source='assigned_to.last_name')
#     #email = serializers.ReadOnlyField(source='assigned_to.email',)

#     class Meta:
#         """Publish Entry Model Serializer Metadata."""
#         model = models.publish_entries.PublishEntry
#         fields = ("editors","editors_id")


class PublishEntryListEditorSerializer(serializers.Serializer):
    """Publish Entry Model Serializer.""" 
    user_id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.CharField()

    class Meta:
        """Publish Entry Model Serializer Metadata."""
        #model = models.publish_entries.PublishEntry
        fields = ('user_id','first_name','last_name', 'email')