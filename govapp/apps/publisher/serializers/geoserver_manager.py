"""Serializers for the kb_geoserver_manager API."""

# Standard
import pathlib

# Third-Party
from rest_framework import serializers

# Local
from govapp.apps.publisher.models.geoserver_queues import GeoServerQueue, GeoServerQueueStatus


class GeoServerManagerQueueSerializer(serializers.ModelSerializer):
    """Serializer exposing GeoServerQueue fields needed by kb_geoserver_manager."""

    # Human-readable name of the publish entry
    name = serializers.CharField(source="publish_entry.name", read_only=True)
    # Basename of the converted file — this is the filename the download endpoint will serve
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = GeoServerQueue
        fields = ["id", "name", "status", "file_name"]
        read_only_fields = ["id", "name", "file_name"]

    def get_file_name(self, obj: GeoServerQueue) -> str | None:
        if obj.converted_file_path:
            return pathlib.Path(obj.converted_file_path).name
        return None


class GeoServerManagerStatusUpdateSerializer(serializers.Serializer):
    """Validates the status PATCH payload sent by kb_geoserver_manager.

    Only the three transitions that kb_geoserver_manager is authorised to make are
    accepted; all other values are rejected.
    """

    ALLOWED_STATUSES = {
        GeoServerQueueStatus.UPLOAD_IN_PROGRESS,
        GeoServerQueueStatus.UPLOAD_FAILED,
        GeoServerQueueStatus.READY_TO_PUBLISH,
    }

    status = serializers.IntegerField()

    def validate_status(self, value: int) -> int:
        if value not in self.ALLOWED_STATUSES:
            allowed_labels = {
                GeoServerQueueStatus.UPLOAD_IN_PROGRESS: "upload_in_progress",
                GeoServerQueueStatus.UPLOAD_FAILED: "upload_failed",
                GeoServerQueueStatus.READY_TO_PUBLISH: "ready_to_publish",
            }
            raise serializers.ValidationError(
                f"Invalid status '{value}'. kb_geoserver_manager may only set: "
                + ", ".join(f"{v} ({k})" for k, v in allowed_labels.items())
            )
        return value
