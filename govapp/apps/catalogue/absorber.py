"""Kaartdijin Boodja Catalogue Django Application Absorber."""


# Standard
import datetime
import logging
import pathlib
import shutil

# Third-Party
from django import conf
from django.db import transaction

# Local
from . import emails
from . import models
from . import sharepoint
from . import utils
from ..accounts import utils as accounts_utils
from ...gis import readers


# Logging
log = logging.getLogger(__name__)


class Absorber:
    """Absorbs new layers into the system."""

    def __init__(self) -> None:
        """Instantiates the Absorber."""
        # Storage
        self.storage = sharepoint.SharepointStorage()

    def absorb(self, path: str) -> None:
        """Absorbs new layers into the system.

        Args:
            path (str): File to absorb.
        """
        # Log
        log.info(f"Retrieving '{path}' from storage")

        # Retrieve file from remote storage
        # This retrieves and writes the file to our own temporary filesystem
        filepath = self.storage.get(path)

        # Move the file on the remote storage into the archive area
        # The file is renamed to include a UTC timestamp, to avoid collisions
        timestamp = datetime.datetime.utcnow()
        timestamp_str = timestamp.strftime("%Y%m%dT%H%M%S")
        archive_directory = f"{conf.settings.SHAREPOINT_ARCHIVE_AREA}/{timestamp.year}"
        archive_path = f"{archive_directory}/{filepath.stem}.{timestamp_str}{filepath.suffix}"
        archive = self.storage.put(archive_path, filepath.read_bytes())  # Move file to archive
        self.storage.delete(path)  # Delete file in staging area

        # Log
        log.info(f"Retrieved '{path}' -> '{filepath}'")
        log.info(f"Archived '{path}' -> {archive_path} ({archive})")

        # Construct Reader
        reader = readers.reader.FileReader(filepath)

        # Loop through layers
        for layer in reader.layers():
            # Log
            log.info(f"Absorbing layer '{layer.name}' from '{filepath}'")

            # Absorb layer
            self.absorb_layer(filepath, layer, archive)

        # Delete local temporary copy of file if we can
        shutil.rmtree(filepath.parent, ignore_errors=True)

    def absorb_layer(self, filepath: pathlib.Path, layer: readers.base.LayerReader, archive: str) -> None:
        """Absorbs a layer into the system.

        Args:
            filepath (pathlib.Path): File to absorb layer from.
            layer (readers.base.LayerReader): Layer to absorb.
            archive (str): URL to the archived file for this layer.
        """
        # Log
        log.info(f"Extracting data from layer: '{layer.name}'")

        # Extract metadata, attributes and symbology
        metadata = layer.metadata()
        attributes = layer.attributes()
        symbology = layer.symbology()

        # Retrieve existing catalogue entry from the database
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.filter(name=metadata.name).first()

        # Check existing catalogue entry
        if not catalogue_entry:
            # Create
            self.create_catalogue_entry(metadata, attributes, symbology, archive)

        else:
            # Update
            self.update_catalogue_entry(catalogue_entry, metadata, attributes, symbology, archive)

    @transaction.atomic()
    def create_catalogue_entry(
        self,
        metadata: readers.types.Metadata,
        attributes: list[readers.types.Attribute],
        symbology: readers.types.Symbology,
        archive: str,
    ) -> bool:
        """Creates a new catalogue entry with the supplied values.

        Args:
            metadata (Metadata): Metadata for the entry.
            attributes (list[Attribute]): Attributes for the entry.
            symbology (Symbology): Symbology for the entry.
            archive (str): Archive URL for the entry

        Returns:
            bool: Whether the creation was successful.
        """
        # Log
        log.info("Creating new catalogue entry")

        # Calculate attributes hash
        attributes_hash = utils.attributes_hash(attributes)

        # Create Catalogue Entry
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.create(
            name=metadata.name,
            description=metadata.description,
        )

        # Create Layer Submission
        models.layer_submissions.LayerSubmission.objects.create(
            name=metadata.name,
            description=metadata.description,
            file=archive,
            is_active=True,  # Active!
            created_at=metadata.created_at,
            hash=attributes_hash,
            catalogue_entry=catalogue_entry,
        )

        # Create Layer Metadata
        models.layer_metadata.LayerMetadata.objects.create(
            name=metadata.name,
            created_at=metadata.created_at,
            catalogue_entry=catalogue_entry,
        )

        # Loop through attributes
        for attribute in attributes:
            # Create Attribute
            models.layer_attributes.LayerAttribute.objects.create(
                name=attribute.name,
                type=attribute.type,
                order=attribute.order,
                catalogue_entry=catalogue_entry,
            )

        # Create Layer Symbology
        models.layer_symbology.LayerSymbology.objects.create(
            name=symbology.name,
            sld=symbology.sld,
            catalogue_entry=catalogue_entry,
        )

        # Publish Layer and Symbology
        catalogue_entry.active_layer.publish()
        catalogue_entry.symbology.publish()

        # Send Emails!
        emails.CatalogueEntryCreatedEmail().send_to_users(
            *accounts_utils.all_administrators(),  # Send to all administrators
        )

        # Return
        return True

    @transaction.atomic()
    def update_catalogue_entry(
        self,
        catalogue_entry: models.catalogue_entries.CatalogueEntry,
        metadata: readers.types.Metadata,
        attributes: list[readers.types.Attribute],
        symbology: readers.types.Symbology,
        archive: str,
    ) -> bool:
        """Creates a new catalogue entry with the supplied values.

        Args:
            catalogue_entry (CatalogueEntry): Catalogue entry to update.
            metadata (Metadata): Metadata for the entry.
            attributes (list[Attribute]): Attributes for the entry.
            symbology (Symbology): Symbology for the entry.
            archive (str): Archive URL for the entry.

        Returns:
            bool: Whether the update was successful.
        """
        # Log
        log.info("Updating existing catalogue entry")

        # Calculate Layer Submission Attributes Hash
        attributes_hash = utils.attributes_hash(attributes)

        # Create New Layer Submission
        layer_submission = models.layer_submissions.LayerSubmission.objects.create(
            name=metadata.name,
            description=metadata.description,
            file=archive,
            is_active=False,  # Starts out Inactive
            created_at=metadata.created_at,
            hash=attributes_hash,
            catalogue_entry=catalogue_entry,
        )

        # Attempt to "Activate" this Layer Submission
        layer_submission.activate()

        # Check Success
        success = not layer_submission.is_declined()

        # Check Layer Submission
        if success:
            # Publish Layer
            catalogue_entry.active_layer.publish()

            # Send Update Success Email
            emails.CatalogueEntryUpdateSuccessEmail().send_to_users(
                *accounts_utils.all_administrators(),  # Send to all administrators
                *catalogue_entry.editors.all(),  # Send to all editors
            )

        else:
            # Send Update Failure Email
            emails.CatalogueEntryUpdateFailEmail().send_to_users(
                *accounts_utils.all_administrators(),  # Send to all administrators
                *catalogue_entry.editors.all(),  # Send to all editors
            )

        # Return
        return success
