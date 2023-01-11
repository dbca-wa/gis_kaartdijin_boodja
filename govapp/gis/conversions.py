"""GIS Conversion Functionality."""


# Standard
import logging
import pathlib
import subprocess  # noqa: S404
import tempfile

# Local
from . import compression


# Logging
log = logging.getLogger(__name__)


def to_geopackage(filepath: pathlib.Path, layer: str) -> pathlib.Path:
    """Converts a GIS file to the GeoPackage format.

    Args:
        filepath (pathlib.Path): Path to the file to be converted.
        layer (str): Layer to be converted.

    Returns:
        pathlib.Path: Path to the converted GeoPackage file.
    """
    # Log
    log.info(f"Converting file '{filepath}' layer: '{layer}' to GeoPackage")

    # Decompress and Flatten if Required
    filepath = compression.decompress(filepath)
    filepath = compression.flatten(filepath)

    # Construct Output Filepath
    output_dir = tempfile.mkdtemp()
    output_filepath = pathlib.Path(output_dir) / f"{layer}.gpkg"

    # Run Command
    subprocess.check_call(  # noqa: S603,S607
        [
            "ogr2ogr",
            "-overwrite",
            str(output_filepath),
            str(filepath),
            str(layer),
        ]
    )

    # Return
    return output_filepath
