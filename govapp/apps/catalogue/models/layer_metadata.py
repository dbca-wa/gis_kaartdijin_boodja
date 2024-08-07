"""Kaartdijin Boodja Catalogue Django Application Layer Metadata Models."""


# Third-Party
from django.db import models
import reversion

# Local
from govapp.common import mixins
from govapp.apps.catalogue.models import catalogue_entries


@reversion.register()
class LayerMetadata(mixins.RevisionedMixin):
    """Model for a Layer Metadata."""
    created_at = models.DateTimeField()
    catalogue_entry = models.OneToOneField(
        catalogue_entries.CatalogueEntry,
        related_name="metadata",
        on_delete=models.CASCADE,
    )
    additional_data = models.JSONField(null=True, blank=True)

    class Meta:
        """Layer Metadata Model Metadata."""
        verbose_name = "Layer Metadata"
        verbose_name_plural = "Layer Metadata"

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
