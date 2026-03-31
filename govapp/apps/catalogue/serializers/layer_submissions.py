"""Kaartdijin Boodja Catalogue Django Serializers."""


# Third-Party
import pytz
from rest_framework import serializers

# Local
from govapp.apps.catalogue import models


class LayerSubmissionSerializer(serializers.ModelSerializer):
    """Layer Submission Model Serializer."""
    submitted_at_str = serializers.SerializerMethodField()
    class Meta:
        """Layer Submission Model Serializer Metadata."""
        model = models.layer_submissions.LayerSubmission
        fields = (
            "id",
            "name",
            "description",
            "file",
            "file_size",
            "is_active",
            "status",
            "status_name",
            "submitted_at",
            "submitted_at_str",
            "created_at",
            "catalogue_entry",
            "permission_type",
            "permission_type_str",
            "crs",
        )
        read_only_fields = (
            "id",
            "name",
            "description",
            "file",
            "file_size",
            "is_active",
            "status",
            "status_name",
            "submitted_at",
            "submitted_at_str",
            "created_at",
            "catalogue_entry",
            "permission_type",
            "permission_type_str",
            "crs",
        )

    def get_submitted_at_str(self, obj):
        if obj.submitted_at:
            local_time = obj.submitted_at.astimezone(pytz.timezone('Australia/Perth'))
            return local_time.strftime('%d-%m-%Y %H:%M:%S')
        return None