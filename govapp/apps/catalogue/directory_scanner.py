"""Kaartdijin Boodja Catalogue Django Application Scanner."""


# Standard
import logging
import os 

# Third-Party
from django import conf

# Local
from govapp.common import local_storage
from govapp.apps.catalogue import directory_absorber
from govapp.apps.catalogue import notifications


# Logging
log = logging.getLogger(__name__)


class Scanner:
    """Scans for files to be absorbed into the system."""

    def __init__(self) -> None:
        """Instantiates the Scanner."""
        # Storage        
        self.storage = local_storage.LocalStorage()

    def scan(self) -> None:
        """Scans for new files in the staging area to be absorbed."""
        # Log
        log.info(f"Scanning storage staging area: [{self.storage.get_pending_import_path()}] for files to absorb")

        # Retrieve file from remote storage staging area
        import os

        files_array = os.listdir(self.storage.get_pending_import_path())

        # Check for files
        if not files_array:
            # Log
            log.info("No files found")

        # Loop through files
        for file in files_array:
            # Skip files that are still being uploaded (written with .tmp suffix)
            # Also skip the companion .tmp.size metadata files created during chunked upload
            if file.endswith('.tmp') or file.endswith('.tmp.size'):
                log.info(f"Skipping '{file}' as it is still being uploaded")
                continue

            # Log
            log.info(f"Discovered file '{file}'")

            # Handle errors
            # For example, if someone drops in a malformed file or a non-GIS file
            try:
                # Absorb!
                directory_absorber.Absorber().absorb(file)

            except Exception as exc:
                # Log and continue
                log.error(f"Error absorbing file '{file}': {exc}")

                # Notify!                
                #notifications.file_absorb_failure(file)

        # Log
        log.info("Scanning storage staging area complete!")
