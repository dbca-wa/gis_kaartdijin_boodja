"""Kaartdijin Boodja Catalogue Django Serializers."""


# Third-Party
import pytz
from rest_framework import serializers

# Local
from govapp.apps.catalogue import models


class CatalogueEntrySerializer(serializers.ModelSerializer):
    """Catalogue Entry Model Serializer."""
    active_layer = serializers.PrimaryKeyRelatedField(read_only=True)  # type: ignore[var-annotated]
    custodian_name = serializers.ReadOnlyField(source='custodian.name',)
    assigned_to_first_name = serializers.ReadOnlyField(source='assigned_to.first_name',)
    assigned_to_last_name = serializers.ReadOnlyField(source='assigned_to.last_name',)
    assigned_to_email = serializers.ReadOnlyField(source='assigned_to.email',)
    updated_at = serializers.SerializerMethodField()
    permission_type_str = serializers.SerializerMethodField()

    class Meta:
        """Catalogue Entry Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = (
            "id",
            "name",
            "description",
            "status",
            "created_at",
            "updated_at",
            "custodian",
            "assigned_to",
            "active_layer",
            "type",
            "layers",
            "email_notifications",
            "webhook_notifications",
            "attributes",
            "metadata",
            "symbology",
            "publish_entry",
            "custodian_name",
            "assigned_to_first_name",
            "assigned_to_last_name",
            "assigned_to_email",
            "permission_type",
            "permission_type_str",
            "force_run_postgres_scanner",
            "default_crs",
        )
        read_only_fields = (
            "id",
            "status",
            "created_at",
            "updated_at",
            "assigned_to",
            "active_layer",
            "type",
            "layers",
            "email_notifications",
            "webhook_notifications",
            "attributes",
            "metadata",
            "symbology",
            "publish_entry",
        )

    def get_permission_type_str(self, obj):
        return obj.get_permission_type_display()

    def get_updated_at(self, obj):
        """Convert updated_at to the desired format."""
        if obj.updated_at:
            # Convert to local time
            local_time = obj.updated_at.astimezone(pytz.timezone('Australia/Perth'))
            # Return formatted string
            return local_time.strftime('%d-%m-%Y %H:%M:%S')
        return None


class CatalogueEntryCreateSubscriptionMappingSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        """Layer Subscription Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = (
            "name",
            "description",
            "mapping_name",
            "type",
            "layer_subscription"
        )
    
    def validate(self, data):
        return data

    def validate_name(self, value):
        if models.catalogue_entries.CatalogueEntry.objects.filter(name=value).exists():
            raise serializers.ValidationError("This Catalogue Entry Name is already taken.")
        return value


class CatalogueEntryUpdateSubscriptionMappingSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    mapping_name = serializers.CharField(required=False)
    
    class Meta:
        """Layer Subscription Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = ("name", "description", "mapping_name")

    def validate_name(self, value):
        instance = self.instance
        if models.catalogue_entries.CatalogueEntry.objects.filter(name=value).exclude(id=instance.id).exists():
            raise serializers.ValidationError("This Catalogue Entry Name is already taken.")
        return value


class CatalogueEntryGetSubscriptionMappingSerializer(serializers.ModelSerializer):
    class Meta:
        """Layer Subscription Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = ("name", "description", "mapping_name")
        read_only_fields = ("name", "description", "mapping_name")


class CatalogueEntryCreateSubscriptionQuerySerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        """Layer Subscription Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = ("name", "description", "sql_query")
    
    def validate(self, data):
        if 'sql_query' not in data or not data['sql_query']:
            raise serializers.ValidationError("'sql_query' field is required.")
        return data

    def validate_name(self, value):
        if models.catalogue_entries.CatalogueEntry.objects.filter(name=value).exists():
            raise serializers.ValidationError("This Catalogue Entry Name is already taken.")
        return value


class CatalogueEntryUpdateSubscriptionQuerySerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sql_query = serializers.CharField(required=False)
    force_run_postgres_scanner = serializers.BooleanField(required=False)

    def validate(self, data):
        return data

    def validate_name(self, value):
        instance = self.instance
        if models.catalogue_entries.CatalogueEntry.objects.filter(name=value).exclude(id=instance.id).exists():
            raise serializers.ValidationError("This Catalogue Entry Name is already taken.")
        return value
    
    class Meta:
        """Layer Subscription Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = ("name", "description", "sql_query", "force_run_postgres_scanner")


class CatalogueEntryGetSubscriptionQuerySerializer(serializers.ModelSerializer):
    class Meta:
        """Layer Subscription Model Serializer Metadata."""
        model = models.catalogue_entries.CatalogueEntry
        fields = ("name", "description", "sql_query")
        read_only_fields = ("name", "description", "sql_query")