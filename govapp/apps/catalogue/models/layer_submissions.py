"""Kaartdijin Boodja Catalogue Django Application Layer Submission Models."""


# Third-Party
from django.db import models
import reversion
import logging

# Local
from govapp.common import mixins
from govapp.apps.catalogue import utils
from govapp.apps.catalogue.models import catalogue_entries
from govapp.apps.catalogue.models import layer_metadata

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

    @property
    def name(self) -> str:
        """Proxies the Catalogue Entry's name to this model.

        Returns:
            str: Name of the Catalogue Entry.
        """
        # Retrieve and Return
        return self.catalogue_entry.name
    
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
        # Retrieve String and Return
        return self.submitted_at.strftime(format)

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
            metadata.created_at = self.created_at
            metadata.save()

            # Check if Catalogue Entry is Pending
            if self.catalogue_entry.is_pending():
                # Lock it again
                self.catalogue_entry.lock()

        else:
            # Failure!
            # Do not update Catalogue Entry
            # Create New Inactive Layer Submission with Status DECLINED
            self.status = LayerSubmissionStatus.DECLINED
            self.save()
