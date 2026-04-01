"""Kaartdijin Boodja Publisher Django Application GeoserverPool Models."""


# Third-Party
from django.db import models
from django.utils import timezone
from django.contrib import auth
import reversion

# Local
from govapp.common import mixins

# Typing
from typing import TYPE_CHECKING

# Type Checking
if TYPE_CHECKING:
    from govapp.apps.publisher.models.publish_entries import PublishEntry

# Shortcuts
UserModel = auth.get_user_model()

class GeoServerQueueStatus(models.IntegerChoices):
    READY = 0, "Queued"
    PROCESSING = 1, "Converting"
    PUBLISHED = 2, "Published"
    FAILED = 3, "Conversion Failed"
    CONVERTED = 4, "Awaiting Transfer"
    UPLOAD_IN_PROGRESS = 5, "Transferring"
    UPLOAD_FAILED = 6, "Transfer Failed"
    READY_TO_PUBLISH = 7, "Awaiting Publication"
    PUBLISH_FAILED = 8, "Publication Failed"


class GeoServerQueueType(models.IntegerChoices):
    PUBLISH = 0
    PURGE_CACHE = 1


@reversion.register()
class GeoServerQueue(mixins.RevisionedMixin):
    """Model for an Geoserver Queue."""
    publish_entry = models.ForeignKey(
        to="PublishEntry",
        related_name="geoserver_queues",
        on_delete=models.CASCADE,
    )
    queue_type = models.IntegerField(choices=GeoServerQueueType.choices, default=GeoServerQueueType.PUBLISH)
    symbology_only = models.BooleanField(default=True)
    status = models.IntegerField(choices=GeoServerQueueStatus.choices, default=GeoServerQueueStatus.READY)
    publishing_result = models.TextField(null=True)
    success = models.BooleanField(null=True, default=False)
    submitter = models.ForeignKey(
        to=UserModel, 
        related_name="geoserver_queues", 
        on_delete=models.CASCADE,
        null=True,
        blank=None,
        default=None
        )
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    converted_file_path = models.TextField(null=True, blank=True)
    
    class Meta:
        """Geoserver Queue Model Metadata."""
        verbose_name = "Geoserver Queue"
        verbose_name_plural = "Geoserver Queues"

    @classmethod
    def is_publish_entry_queued(cls, publish_entry: "PublishEntry", queue_type: "GeoServerQueueType" = GeoServerQueueType.PUBLISH) -> bool:
        """Checks if a publish entry is already queued for the given queue type.

        Args:
            publish_entry (PublishEntry): The publish entry to check.
            queue_type (GeoServerQueueType): The type of queue to check. Defaults to PUBLISH.

        Returns:
            bool: True if the publish entry is already queued to be processed, False otherwise.
        """
        # Check if the publish entry is already queued for this specific queue type
        existing = cls.objects.filter(
            publish_entry=publish_entry,
            queue_type=queue_type,
            status__in=[
                GeoServerQueueStatus.READY,
                GeoServerQueueStatus.PROCESSING,
                GeoServerQueueStatus.CONVERTED,
                GeoServerQueueStatus.UPLOAD_IN_PROGRESS,
                GeoServerQueueStatus.READY_TO_PUBLISH,
            ]
        ).exists()
        return existing

    def change_status(self, status: GeoServerQueueStatus) -> None:
        self.status = status
        if status in (GeoServerQueueStatus.PROCESSING, GeoServerQueueStatus.UPLOAD_IN_PROGRESS):
            self.started_at = timezone.now()
        elif status in (GeoServerQueueStatus.PUBLISHED, GeoServerQueueStatus.READY_TO_PUBLISH):
            self.completed_at = timezone.now()
        self.save()
        
    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.id}"
    
