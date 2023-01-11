"""Geopackage GIS Reader."""


# Standard
import datetime
import pathlib

# Local
from .. import base
from .. import types

# Third-Party
from dateutil import parser
from osgeo import ogr


class GeopackageReader(base.LayerReader):
    """Geopackage Layer Reader."""

    @classmethod
    def is_compatible(cls, file: pathlib.Path) -> bool:
        """Determines whether this file is a Geopackage file.

        Args:
            file (pathlib.Path): Path to the file to check.

        Returns:
            bool: Whether this file is compatible with this reader.
        """
        # Check and Return
        # Path must be a file with the suffix `.json`
        return file.is_file() and file.suffix.lower() == ".gpkg"

    def skip(self) -> bool:
        """Determines whether to skip this layer.

        Some Geopackage files (e.g., created by QGIS) have an extra layer
        called `layer_styles` which is not actually a layer - it stores the
        symbology for the other layers. If we encounter this layer, then we
        skip it.

        Returns:
            bool: Whether to skip this layer.
        """
        # Check and Return
        return self.name == "layer_styles"

    def metadata(self) -> types.Metadata:
        """Extracts metadata.

        Returns:
            models.Metadata: Extracted metadata.
        """
        # Extract Name and Description from Metadata
        name = self.name
        description = self.layer.GetMetadataItem("DESCRIPTION") or ""  # Blank

        # Handle Errors
        try:
            # Extract Last Change Datetime with SQL
            layer: ogr.Layer = self.datasource.ExecuteSQL(
                "SELECT last_change "  # noqa: S608
                "FROM gpkg_contents "
                f"WHERE table_name = '{name}'"
            )
            feature: ogr.Feature = layer.GetNextFeature()
            field: str = feature.GetField(0)
            created_at = parser.parse(field)

        except Exception:
            # Use Current Time (UTC)
            created_at = datetime.datetime.now(datetime.timezone.utc)

        # Construct and Return Metadata
        return types.Metadata(
            name=name,
            description=description,
            created_at=created_at,
        )

    def symbology(self) -> types.Symbology:
        """Extracts symbology.

        Returns:
            models.Symbology: Extracted symbology.
        """
        # Try Extract Symbology
        try:
            # Extract Symbology with from Layer Styles Table
            layer: ogr.Layer = self.datasource.GetLayerByName("layer_styles")

            # Filter
            layer.SetAttributeFilter(f"f_table_name = '{self.name}'")

            # Get Feature
            feature: ogr.Feature = layer.GetNextFeature()

            # Get Style Name and SLD Indexes
            name_index: int = feature.GetFieldIndex("styleName")
            sld_index: int = feature.GetFieldIndex("styleSLD")

            # Get Style Name and SLD
            name: str = feature.GetField(name_index)
            sld: str = feature.GetField(sld_index)

            # Construct Symbology
            symbology = types.Symbology(
                name=name,
                sld=sld,
            )

        except Exception:
            # Retrieve Default Symbology
            symbology = super().symbology()

        # Return Symbology
        return symbology
