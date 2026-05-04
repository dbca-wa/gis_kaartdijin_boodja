"""Kaartdijin Boodja Catalogue Django Application Allowed CRS Models."""

# Third-Party
import reversion
from django.db import models


@reversion.register()
class AllowedCRS(models.Model):
    """Model representing a CRS code that is permitted for spatial file uploads."""

    epsg_code = models.CharField(
        max_length=64,
        unique=True,
        help_text="EPSG CRS identifier, e.g. 'EPSG:7844'.",
    )
    label = models.CharField(
        max_length=256,
        help_text="Human-readable name, e.g. 'GDA2020'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Allowed CRS"
        verbose_name_plural = "Allowed CRS"
        ordering = ["epsg_code"]

    def __str__(self) -> str:
        return f"{self.label} ({self.epsg_code})"
