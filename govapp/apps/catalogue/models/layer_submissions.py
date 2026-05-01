"""Kaartdijin Boodja Catalogue Django Application Layer Submission Models."""


# Third-Party
from django.db import models
from django.utils import timezone as django_timezone
import reversion
import logging
import requests

# Local
from govapp.apps.catalogue.models.permission import CatalogueEntryAccessPermission, CatalogueEntryPermission
from govapp.common import mixins
from govapp.apps.catalogue import utils
from govapp.apps.catalogue.models import catalogue_entries
from govapp.apps.catalogue.models import layer_metadata
from govapp.apps.logs import utils as logs_utils

# Typing
from typing import cast


# Logging
log = logging.getLogger(__name__)


class LayerSubmissionStatus(models.IntegerChoices):
    """Enumeration for a Layer Submission Status."""
    SUBMITTED = 1
    ACCEPTED = 2
    DECLINED = 3

@reversion.register()
class LayerSubmission(mixins.RevisionedMixin):
    """Model for a Layer Submission."""
    description = models.TextField(blank=True)
    file = models.URLField()
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes.")
    is_active = models.BooleanField()
    status = models.IntegerField(choices=LayerSubmissionStatus.choices, default=LayerSubmissionStatus.SUBMITTED)
    created_at = models.DateTimeField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    hash = models.TextField()  # noqa: A003
    catalogue_entry = models.ForeignKey(
        catalogue_entries.CatalogueEntry,
        related_name="layers",
        on_delete=models.CASCADE,
    )
    layer_attribute = models.TextField(null=True, blank=True, help_text="This is the attribute data from the spatial file.")
    geojson = models.TextField(null=True, blank=True)
    crs = models.CharField(max_length=64, null=True, blank=True, help_text="CRS of the submitted spatial file, e.g. 'EPSG:7844'.")

    class Meta:
        """Layer Submission Model Metadata."""
        verbose_name = "Layer Submission"
        verbose_name_plural = "Layer Submissions"

    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.name}"
    
    def save(self, *args, **kwargs):
        # When the model is saved, try to fetch the file size
        if self.file and not self.file_size:
            try:
                # Use a HEAD request to get headers without downloading the full file
                response = requests.head(self.file, allow_redirects=True, timeout=5) # 5 second timeout
                response.raise_for_status()

                # Get the file size from the 'Content-Length' header
                size = response.headers.get('Content-Length')
                if size:
                    self.file_size = int(size)

            except requests.exceptions.RequestException as e:
                # If there's a network error or the URL is invalid,
                # we can log the error and leave file_size as null.
                log.error(f"Could not fetch file size for [{self.file}: {e}")
                pass

        super().save(*args, **kwargs) # Call the "real" save() method.
    
    @property
    def is_restricted(self):
        return self.catalogue_entry.is_restricted

    def get_user_access_permission(self, user):
        return self.catalogue_entry.get_user_access_permission(user)

    @property
    def name(self) -> str:
        """Proxies the Catalogue Entry's name to this model.

        Returns:
            str: Name of the Catalogue Entry.
        """
        # Retrieve and Return
        return self.catalogue_entry.name
    
    @property
    def permission_type_str(self):
        return self.catalogue_entry.get_permission_type_display()

    @property
    def permission_type(self):
        return self.catalogue_entry.permission_type
    
    @property
    def status_name(self) -> str:
        """
        Provides the Status name to this model.

        Returns:
            str: Name of the Status 
        """
        # Retrieve String and Return
        status = utils.find_enum_by_value(LayerSubmissionStatus, self.status)
        return status.name
    
    @property
    def submit_datetime(self, format="%d-%m-%Y %H:%M:%S") -> str:
        """
        Provides the Formatted datetime string to this model.

        Returns:
            str: Formatted datetime string of the submitted_at 
        """
        # Retrieve String and Return (convert UTC → Perth local time before formatting)
        local_dt = django_timezone.localtime(self.submitted_at)
        return local_dt.strftime(format)

    def is_declined(self) -> bool:
        """Determines whether the Layer Submission is declined.

        Returns:
            bool: Whether the Layer Submission is declined.
        """
        # Check and Return
        return self.status == LayerSubmissionStatus.DECLINED

    def accept(self) -> None:
        """Accepts the Layer Submission."""
        # Set Status and Save
        self.status = LayerSubmissionStatus.ACCEPTED
        self.save()

    def decline(self) -> None:
        """Declines the Layer Submission."""
        # Set Status and Save
        self.status = LayerSubmissionStatus.DECLINED
        self.save()

    def activate(self, raise_err=True) -> None:
        """Updates the Layer Submission's Catalogue Entry with this layer."""
        log.info(f'Activating the LayerSubmission: [{self}]...')
        # Check the created date?
        # TODO
        ...

        # Calculate the Catalogue Entry's attributes hash
        attributes_hash = utils.attributes_hash(self.catalogue_entry.attributes.all())
        log.info(f"The attributes_hash of the LayerSubmission: [{self}] is [{attributes_hash}].")
        log.info(f"Current attribute_hash is [{self.hash}]")

        # Check if they match!
        # Also check that Catalogue Entry is not declined
        if self.hash == attributes_hash and not self.catalogue_entry.is_declined():
            # Retrieve Catalogue Entry's Current Active Layer
            current_active_layer = None
            try:
                current_active_layer = self.catalogue_entry.active_layer
            except AssertionError as err:
                # If there was no active layer, this one should be active if needed.
                if raise_err:
                    raise err

            # Determine behaviour based on current status
            if self.catalogue_entry.is_new():
                # Catalogue Entry is new
                # Set the new incoming layer submission to SUBMITTED
                # Set the old active layer to DECLINED
                self.status = LayerSubmissionStatus.SUBMITTED
                if current_active_layer is not None:
                    current_active_layer.status = LayerSubmissionStatus.DECLINED

            else:
                # Set the new incoming layer submission to ACCEPTED
                self.status = LayerSubmissionStatus.ACCEPTED

            # Update!
            # Update Current Active Layer to Inactive
            # Update New Active Layer to Active
            if current_active_layer is not None:
                current_active_layer.is_active = False
                current_active_layer.save()
            self.is_active = True
            self.save()

            # Update the Catalogue Entry Metadata's Datetime
            # Help `mypy` by casting the object to a Layer Metadata
            metadata = self.catalogue_entry.metadata
            metadata = cast(layer_metadata.LayerMetadata, metadata)
            # metadata.created_at = self.created_at
            metadata.save()

            # Check if Catalogue Entry is Pending
            if self.catalogue_entry.is_pending():
                # Lock it again
                self.catalogue_entry.lock()

        else:
            # Failure!
            # Do not update Catalogue Entry
            # Create New Inactive Layer Submission with Status DECLINED
            if self.catalogue_entry.is_declined():
                decline_reason = (
                    f"Layer submission LM{self.pk} was declined: "
                    f"the catalogue entry '{self.catalogue_entry}' is already in DECLINED status."
                )
                log.warning(decline_reason)
            elif self.hash != attributes_hash:
                decline_reason = (
                    f"Layer submission LM{self.pk} was declined: "
                    f"the column structure of the uploaded file does not match the previously accepted file "
                    f"(attributes hash mismatch)."
                )
                log.warning(
                    f"{decline_reason} "
                    f"Submission hash: [{self.hash}], "
                    f"CatalogueEntry attributes hash: [{attributes_hash}]."
                )
            else:
                decline_reason = f"Layer submission LM{self.pk} was declined."
                log.warning(decline_reason)
            logs_utils.add_to_actions_log(
                user=None,
                model=self.catalogue_entry,
                action=decline_reason,
                default_to_system=True,
            )
            self.status = LayerSubmissionStatus.DECLINED
            self.save()
