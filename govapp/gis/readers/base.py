"""Base class for reading GIS layers."""


# Standard
import abc
import datetime
import pathlib

# Local
from . import types

# Third-Party
from osgeo import ogr


# Load Default SLD
DEFAULT_SLD = pathlib.Path(__file__).with_name("default.sld").read_text()


class LayerReader(abc.ABC):
    """Layer Reader Abstract Base Class."""

    def __init_subclass__(cls) -> None:
        """Registers subclass."""
        # Register subclass
        readers.add(cls)

    def __init__(
        self,
        file: pathlib.Path,
        datasource: ogr.DataSource,
        layer: ogr.Layer,
    ) -> None:
        """Instantiates the Layer Reader.

        Args:
            file (pathlib.Path): Filepath to read.
            datasource (ogr.DataSource): Interal OGR DataSource to be read.
            layer (ogr.Layer): Interal OGR Layer to be read.
        """
        # Store the File, Data Source and Layer Objects
        self.file = file
        self.datasource = datasource
        self.layer = layer

    @property
    def name(self) -> str:
        """Retrieves the name of the layer.

        Returns:
            str: Name of the layer.
        """
        # Retrieve and Return
        return self.layer.GetName()  # type: ignore[no-any-return]

    @classmethod
    @abc.abstractmethod
    def is_compatible(cls, file: pathlib.Path) -> bool:
        """Determines whether the file and layer is compatible with the reader.

        Args:
            file (pathlib.Path): Filepath to read.

        Returns:
            bool: Whether this Layer Reader can read the file and layer.
        """
        # Must be implemented on subclass
        raise NotImplementedError

    def skip(self) -> bool:
        """Determines whether to skip this layer.

        The default behaviour on the base class is to not skip any layers. For
        some formats (e.g., Geopackage), extra data (e.g., symbology / styling)
        is stored as an extra layer. In these cases, we need to skip the
        parsing of these layers manually on the subclass.

        Returns:
            bool: Whether to skip this layer.
        """
        # Return
        return False

    def attributes(self) -> list[types.Attribute]:
        """Extracts attributes.

        The default behaviour on the base class is to use GDAL (ogr) to extract
        the attributes from the layer. This is standard functionality and
        should be the same for most GIS formats.

        Returns:
            list[models.Attribute]: List of extracted attributes.
        """
        # Construct Attributes List
        attributes: list[types.Attribute] = []

        # Get Layer Definition
        layer_defn: ogr.FeatureDefn = self.layer.GetLayerDefn()

        # Get Attributes Count
        attributes_count: int = layer_defn.GetFieldCount()

        # Loop through Attribute Indexes
        for attribute_index in range(attributes_count):
            # Get Attribute Definition
            attribute_defn: ogr.FieldDefn = layer_defn.GetFieldDefn(attribute_index)

            # Construct Attribute
            attribute = types.Attribute(
                name=attribute_defn.GetName(),
                type=attribute_defn.GetFieldTypeName(attribute_defn.GetType()),
                order=attribute_index + 1,
            )

            # Append Attribute
            attributes.append(attribute)

        # Return
        return attributes

    def metadata(self) -> types.Metadata:
        """Extracts metadata.

        The default behaviour on the base class is to extract the layer name
        using GDAL (ogr), leave the description blank and use the current time
        (UTC) as the creation timestamp. This is because every layer has a
        name, but there is no standard way to include a description or creation
        timestamp in every format. If those are included in the GIS file, then
        they must be extracted manually on the subclass.

        Returns:
            models.Metadata: Extracted metadata.
        """
        # Construct and Return Metadata
        return types.Metadata(
            name=self.name,  # Layer Name from GDAL
            description="",  # Blank by Default
            created_at=datetime.datetime.now(datetime.timezone.utc),  # Current Time by Default
        )

    def symbology(self) -> types.Symbology:
        """Extracts symbology.

        The default behaviour on the base class is to return an empty symbology
        representation, assuming that the file has no symbology. This is
        because there is no standard way to include symbology (styling) in
        every format. As such, if it is included it must be extracted manually
        on the subclass.

        Returns:
            models.Symbology: Extracted symbology.
        """
        # Construct and Return Empty Symbology
        return types.Symbology(
            name=self.name,  # Layer Name from GDAL
            sld=DEFAULT_SLD,  # Default Empty SLD
        )


# Readers Registry
readers: set[type[LayerReader]] = set()
