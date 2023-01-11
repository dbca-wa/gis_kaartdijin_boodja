"""Model Factories for the Catalogue Layer Symbology Model."""


# Third-Party
import factory

# Local
from govapp.apps.catalogue import models
from govapp.gis.readers import base


class LayerSymbologyFactory(factory.django.DjangoModelFactory):
    """Factory for a Layer Symbology."""
    name = factory.Sequence(lambda n: f"Layer Symbology {n + 1}")
    sld = base.DEFAULT_SLD

    class Meta:
        """Layer Symbology Factory Metadata."""
        model = models.layer_symbology.LayerSymbology
