"""Provides unit tests for the GIS reader formats."""


# Standard
import datetime
import yaml

# Local
from govapp.gis import readers
from tests import utils

# Third-Party
import freezegun
import pytest


@pytest.mark.parametrize(
    (
        "data_file",
        "yaml_file",
    ),
    [
        ("gdb/100kMapsheetIndex_sgl_lyr.gdb.7z", "gdb/100kMapsheetIndex_sgl_lyr.gdb.yaml"),
        ("gdb/GDB_4lyr_w_2_sld.7z", "gdb/GDB_4lyr_w_2_sld.yaml"),
        ("gdb/Plantations_4_layers.gdb.7z", "gdb/Plantations_4_layers.gdb.yaml"),
        ("geojson/regions.geojson", "geojson/regions.yaml"),
        ("gpkg/Admin_boundaries.gpkg", "gpkg/Admin_boundaries.yaml"),
        ("gpkg/Local_areas_styled.gpkg", "gpkg/Local_areas_styled.yaml"),
        ("gpkg/WA_coast.gpkg", "gpkg/WA_coast.yaml"),
        ("shp/cog_index_w_sld.7z", "shp/cog_index_w_sld.yaml"),
        ("shp/World_Heritage.7z", "shp/World_Heritage.yaml"),
    ],
)
@freezegun.freeze_time("2022-12-17")
def test_formats(data_file: str, yaml_file: str) -> None:
    """Tests the reading of parametrized GIS files."""
    # Filepath
    data_filepath = utils.test_file(data_file)
    yaml_filepath = utils.test_file(yaml_file)

    # Load YAML File
    expected = yaml.safe_load(yaml_filepath.open())
    expected = expected["layers"]

    # Copy to a Temporary Directory
    temporary_filepath = utils.to_temporary_directory(data_filepath)

    # Instantiate Reader
    reader = readers.reader.FileReader(temporary_filepath)

    # Read all layers
    layers = list(reader.layers())

    # Assert layers
    assert len(layers) == len(expected)

    # Loop
    for (layer, expected_layer) in zip(layers, expected):
        # Extract metadata
        metadata = layer.metadata()

        # Assert metadata
        assert metadata.name == expected_layer["name"]
        assert metadata.description == (expected_layer["description"] or "")
        assert metadata.created_at == (expected_layer["created_at"] or datetime.datetime.now(datetime.timezone.utc))

        # Extract attributes
        attributes = layer.attributes()

        # Assert attributes
        assert len(attributes) == len(expected_layer["attributes"])

        # Loop
        for (attribute, expected_attribute) in zip(attributes, expected_layer["attributes"]):
            # Assert
            assert attribute.order == expected_attribute[0]
            assert attribute.name == expected_attribute[1]
            assert attribute.type == expected_attribute[2]

        # Extract symbology
        symbology = layer.symbology()

        # Assert
        assert symbology.sld == (expected_layer["symbology"] or readers.base.DEFAULT_SLD)
