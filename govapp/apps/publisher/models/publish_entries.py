"""Kaartdijin Boodja Publisher Django Application Publish Entry Models."""


# Standard
import logging

# Third-Party
from django.contrib import auth
from django.contrib.auth import models as auth_models
from django.db import models
from rest_framework import request
import reversion

# Local
from govapp.common import mixins
from govapp.apps.accounts import utils as accounts_utils
from govapp.apps.publisher import notifications as notifications_utils
from govapp.apps.catalogue.models import catalogue_entries
from govapp.apps.publisher import geoserver_manager

# Typing
from typing import Optional, Union, TYPE_CHECKING

# Type Checking
if TYPE_CHECKING:
    from govapp.apps.publisher.models import notifications
    # from govapp.apps.publisher.models import publish_channels
    from govapp.apps.publisher.models import geoserver_queues


# Shortcuts
UserModel = auth.get_user_model()

# Logging
log = logging.getLogger(__name__)


class PublishEntryStatus(models.IntegerChoices):
    """Enumeration for a Publish Entry Status."""
    LOCKED = 1
    UNLOCKED = 2


class PublishEntryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().prefetch_related('geoserver_channels', 'cddp_channels', 'ftp_channels')


@reversion.register()
class PublishEntry(mixins.RevisionedMixin):
    """Model for a Publish Entry."""
    description = models.TextField(blank=True)
    status = models.IntegerField(choices=PublishEntryStatus.choices, default=PublishEntryStatus.LOCKED)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)
    editors = models.ManyToManyField(
        UserModel,
        blank=True,
        limit_choices_to=accounts_utils.limit_to_administrators,  # type: ignore[arg-type]
    )
    assigned_to = models.ForeignKey(
        UserModel,
        default=None,
        blank=True,
        null=True,
        related_name="assigned_publish",
        on_delete=models.SET_NULL,
    )
    catalogue_entry = models.OneToOneField(
        catalogue_entries.CatalogueEntry,
        related_name="publish_entry",
        on_delete=models.CASCADE,
    )
    objects = PublishEntryManager()

    # Type Hints for Reverse Relations
    # These aren't exactly right, but are useful for catching simple mistakes.
    # ftp_channel: "Optional[publish_channels.FTPPublishChannel]"
    # cddp_channel: "Optional[publish_channels.CDDPPublishChannel]"
    # geoserver_channel: "Optional[publish_channels.GeoServerPublishChannel]"
    # geoserver_channels: "models.Manager[publish_channels.GeoServerPublishChannel]"
    email_notifications: "models.Manager[notifications.EmailNotification]"
    geoserver_queues: "models.Manager[geoserver_queues.GeoServerQueue]"

    class Meta:
        """Publish Entry Model Metadata."""
        verbose_name = "Publish Entry"
        verbose_name_plural = "Publish Entries"

    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"PE:{self.id}: {self.name}"

    @property
    def name(self) -> str:
        """Proxies the Catalogue Entry's name to this model.

        Returns:
            str: Name of the Catalogue Entry.
        """
        # Retrieve and Return
        return self.catalogue_entry.name

    @property
    def num_of_cache_enabled_channels(self):
        return self.geoserver_channels.filter(publish_entry=self, active=True, create_cached_layer=True).count()

    @property
    def num_of_geoserver_publish_channels_active(self):
        return self.geoserver_channels.filter(active=True).count() if hasattr(self, 'geoserver_channels') else 0

    @property
    def num_of_geoserver_publish_channels_inactive(self):
        return self.geoserver_channels.filter(active=False).count() if hasattr(self, 'geoserver_channels') else 0

    @property
    def num_of_cddp_publish_channels(self):
        return self.cddp_channels.count() if hasattr(self, 'cddp_channels') else 0

    @property
    def num_of_ftp_publish_channels(self):
        return self.ftp_channels.count() if hasattr(self, 'ftp_channels') else 0

    @property
    def publishable_to_cddp(self):
        return True if self.catalogue_entry.type in catalogue_entries.CATALOGUE_ENTRY_TYPES_ALLOWED_FOR_CDDP else False

    @property
    def publishable_to_ftp(self):
        return True if self.catalogue_entry.type in catalogue_entries.CATALOGUE_ENTRY_TYPES_ALLOWED_FOR_FTP else False
    
    @property
    def publishable_to_geoserver(self):
        return True

    @classmethod
    def from_request(cls, request: request.Request) -> Optional["PublishEntry"]:
        """Retrieves a possible Publish Entry from request data.

        Args:
            request (request.Request): Request to retrieve Publish Entry from.

        Returns:
            Optional[models.publish_entries.PublishEntry]: Publish Entry.
        """
        # Retrieve Possible Publish Entry and Return
        return cls.objects.filter(
            id=request.data.get("publish_entry", -1),  # -1 Sentinel Value for Non-Existent Publish Entry
        ).first()

    def publish(self, symbology_only: bool = False) -> None:
        """Publishes to all channels if applicable.

        Args:
            symbology_only (bool): Flag to only publish symbology.
        """
        # Log
        log.info(f"Publishing '{self.catalogue_entry}' - '{self}' ({symbology_only=})")

        # Publish CDDP
        self.publish_cddp(symbology_only)

        # Publish GeoServer
        self.publish_geoserver(symbology_only)

        # Publish FTP
        self.publish_ftp(symbology_only)        

    def publish_cddp(self, symbology_only: bool = False) -> None:
        """Publishes to CDDP channel if applicable.

        Args:
            symbology_only (bool): Flag to only publish symbology.
        """
        # Check for Publish Channel
        if not hasattr(self, "cddp_channels"):
            # Log
            log.info(f"'{self}' has no CDDP Publish Channel")

            # Exit Early
            return

        # Log
        log.info(f"Publishing '{self.catalogue_entry}' - '{self.cddp_channels}' ({symbology_only=})")
        from govapp.apps.publisher.models.publish_channels import CDDPPublishChannel
        # Handle Errors
        try:
            # Publish!
            publish_channel_obj = CDDPPublishChannel.objects.filter(publish_entry=self.id)
            for pc in publish_channel_obj:
                pc.publish(symbology_only)

            #self.cddp_channel.publish(symbology_only)  # type: ignore[union-attr]

        except Exception as exc:
            # Log
            log.error(f"Unable to publish to CDDP Publish Channel: {exc}")

            # Send Failure Emails
            notifications_utils.publish_entry_publish_failure(self)

        else:
            # Send Success Emails
            notifications_utils.publish_entry_publish_success(self)

    def publish_ftp(self, symbology_only: bool = False) -> None:
        """Publishes to FTP channel if applicable.

        Args:
            symbology_only (bool): Flag to only publish symbology.
        """
        # Check for Publish Channel
        if not hasattr(self, "ftp_channels"):
            # Log
            log.info(f"'{self}' has no FTP Publish Channel")

            # Exit Early
            return

        # Log
        log.info(f"FTP Publishing '{self.catalogue_entry}' - '{self.cddp_channels}' ({symbology_only=})")
        from govapp.apps.publisher.models.publish_channels import FTPPublishChannel
        # Handle Errors
        try:
            # Publish!
            publish_channel_obj = FTPPublishChannel.objects.filter(publish_entry=self.id)
            for pc in publish_channel_obj:
                pc.publish(symbology_only)

            #self.cddp_channel.publish(symbology_only)  # type: ignore[union-attr]

        except Exception as exc:
            # Log
            log.error(f"Unable to publish to CDDP Publish Channel: {exc}")

            # Send Failure Emails
            notifications_utils.publish_entry_publish_failure(self)

        else:
            # Send Success Emails
            notifications_utils.publish_entry_publish_success(self)

    def publish_geoserver(self, symbology_only: bool = False) -> None:
        """Push a publish cron job to GeoServer Queue and will be excuted later by cron

        Args:
            symbology_only (bool): Flag to only publish symbology.
        """
        geoserver_manager.push(publish_entry=self, symbology_only=symbology_only)
        
    def is_locked(self) -> bool:
        """Determines whether the Publish Entry is locked.

        Returns:
            bool: Whether the Publish Entry is locked.
        """
        # Check and Return
        return self.status == PublishEntryStatus.LOCKED

    def is_unlocked(self) -> bool:
        """Determines whether the Publish Entry is unlocked.

        Returns:
            bool: Whether the Publish Entry is unlocked.
        """
        # Check and Return
        return self.status == PublishEntryStatus.UNLOCKED

    def is_editor(self, user: Union[auth_models.User, auth_models.AnonymousUser]) -> bool:
        """Checks whether the user is one of this Publish Entry's editors.

        Args:
            user (Union[models.User, models.AnonymousUser]): User to be checked

        Returns:
            bool: Whether the user is one of this Publish entry's editors.
        """
        # Check and Return
        return self.editors.all().filter(id=user.id).exists()

    def lock(self) -> bool:
        """Locks the Publish Entry.

        Returns:
            bool: Whether the locking was successful.
        """
        # Check Publish Entry
        if self.is_unlocked():
            # Set Publish Entry to Locked
            self.status = PublishEntryStatus.LOCKED
            self.save()

            # Send Emails
            notifications_utils.publish_entry_lock(self)

            # Success!
            return True

        # Failed
        return False

    def unlock(self) -> bool:
        """Unlocks the Publish Entry.

        Returns:
            bool: Whether unlocking was successful.
        """
        # Check Publish Entry
        if self.is_locked():
            # Set Publish Entry to Unlocked
            self.status = PublishEntryStatus.UNLOCKED
            self.save()

            # Success!
            return True

        # Failed
        return False

    def assign(self, user: auth_models.User) -> bool:
        """Assigns a user to the Publish Entry if applicable.

        Args:
            user (auth_models.User): User to be assigned.

        Returns:
            bool: Whether the assigning was successful.
        """
        # Check if the user can be assigned
        # To be assigned, a user must be:
        # 1. In the Administrators group
        # 2. One of this Catalogue Entry's editors
        if accounts_utils.is_administrator(user): # and self.is_editor(user):
            # Assign user
            self.assigned_to = user
            self.save()

            # Success!
            return True

        # Failed
        return False

    def unassign(self) -> bool:
        """Unassigns the Publish Entry's user if applicable.

        Returns:
            bool: Whether the unassigning was successful.
        """
        # Check if there is an assigned user
        if self.assigned_to is not None:
            # Unassign
            self.assigned_to = None
            self.save()

            # Success!
            return True

        # Failed
        return False
