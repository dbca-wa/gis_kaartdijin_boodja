"""Kaartdijin Boodja Catalogue Django Application Scanner."""


# Standard
import logging

# Third-Party
from django import conf

# Local
from . import absorber
from . import storage


# Logging
log = logging.getLogger(__name__)


class Scanner:
    """Scans for files to be absorbed into the system."""

    def __init__(self) -> None:
        """Instantiates the Scanner."""
        # Storage
        self.storage = storage.sharepoint.SharepointStorage(
            url=conf.settings.SHAREPOINT_URL,
            root=conf.settings.SHAREPOINT_LIST,
            username=conf.settings.SHAREPOINT_USERNAME,
            password=conf.settings.SHAREPOINT_PASSWORD,
        )

    def scan(self) -> None:
        """Scans for new files in the staging area to be absorbed."""
        # Log
        log.info("Scanning storage staging area for files to absorb")

        # Retrieve file from remote storage staging area
        files = self.storage.list(conf.settings.SHAREPOINT_STAGING_AREA)

        # Check for files
        if not files:
            # Log
            log.info("No files found")

        # Loop through files
        for file in files:
            # Log
            log.info(f"Discovered file '{file}'")

            # Handle errors
            # For example, if someone drops in a malformed file or a non-GIS file
            try:
                # Absorb!
                absorber.Absorber().absorb(file)

            except Exception as exc:
                # Log and continue
                log.error(f"Error absorbing file '{file}': {exc}")

        # Log
        log.info("Scanning storage staging area complete!")
