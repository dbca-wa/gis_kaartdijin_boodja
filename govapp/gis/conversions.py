"""GIS Conversion Functionality."""


# Standard
import logging
import pathlib
import subprocess  # noqa: S404
import tempfile
from osgeo import gdal

# Local
from govapp.gis import compression


# Logging
log = logging.getLogger(__name__)


def to_geopackage(filepath: pathlib.Path, layer: str, catalogue_name: str, export_method: str) -> dict:
    """Converts a GIS file to the GeoPackage format.

    Args:
        filepath (pathlib.Path): Path to the file to be converted.
        layer (str): Layer to be converted.

    Returns:
        pathlib.Path: Path to the converted GeoPackage file.
    """
    log.info(f"Converting file '{filepath}' layer: '{layer}' to GeoPackage...")

    try:
        # Decompress and Flatten if Required
        filepath = compression.decompress(filepath)
        filepath = compression.flatten(filepath)

        # Construct Output Filepath
        output_dir = tempfile.mkdtemp()
        output_filepath = pathlib.Path(output_dir) / f"{layer}.gpkg"

        # --- START: NEW LOGIC TO DETECT RASTER/VECTOR ---
        is_raster = filepath.suffix.lower() in ['.tif', '.tiff']
        command = []

        if is_raster:
            # --- RASTER CONVERSION PATH (using gdal_translate) ---
            log.info(f"Detected raster file ({filepath.suffix}), using gdal_translate.")
            command = [
                "gdal_translate",
                "-of", "GPKG",                   # Set output format to GeoPackage
                "-co", "RASTER_TABLE=" + layer,  # Set the name of the raster table inside the GPKG
                "-co", "TILING_SCHEME=GoogleMapsCompatible", # Recommended for performance
                "-co", "COMPRESS=DEFLATE",       # Use lossless compression
                str(filepath),                   # Input file
                str(output_filepath),            # Output file
            ]
        else:
            # --- VECTOR CONVERSION PATH (using ogr2ogr) ---
            log.info(f"Detected vector file ({filepath.suffix}), using ogr2ogr.")
            if export_method =='geoserver':
                command = [
                    "ogr2ogr",
                    "-overwrite",
                    str(output_filepath),
                    str(filepath),
                    str(layer),
                    "-nln",
                    str(layer),
                ]
            else:
                command = [
                    "ogr2ogr",
                    "-update",
                    "-overwrite",
                    "-nln", 
                    str(layer),                 #'Name' box in new CDDP dialogue
                    str(output_filepath),
                    str(filepath),
                    str(catalogue_name)         # Catalogue name
                ]

        if not command:
            raise NotImplementedError(f"File type '{filepath.suffix}' is not supported for GeoPackage conversion.")

        # Run the command
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        log.info(f"GDAL/OGR Output:\n{result.stdout}\n{result.stderr}")
        log.info(f"Success: Converted file [{filepath}] to GeoPackage successfully.")
        
        # Optional but recommended for rasters: Add overviews (pyramids) for better performance
        if is_raster:
            log.info("Adding overviews to the raster GeoPackage...")
            gdaladdo_command = ["gdaladdo", "-r", "average", str(output_filepath), "2", "4", "8", "16"]
            subprocess.run(gdaladdo_command, check=True, capture_output=True, text=True)
            log.info("Overviews added successfully.")

        # raise RuntimeError(
        #     f"DEBUG: Process halted intentionally. "
        #     f"Please inspect the generated GeoPackage file at: {output_filepath}"
        # )

        converted = {"uncompressed_filepath": output_filepath.parent, "full_filepath": output_filepath,  "orignal_filepath": filepath}
        log.info(f'converted: [{converted}]')

        return converted

    except subprocess.TimeoutExpired as e:
        log.error(f"The command has reached a timeout. Error converting file '{filepath}' layer: '{layer}' to GeoPackage: {e}")
        raise RuntimeError(f"Timeout error converting file '{filepath}' layer: '{layer}' to GeoPackage: {e}")
    except subprocess.CalledProcessError as e:
        # Provide more detailed error info from the failed command
        error_message = f"GDAL/OGR command failed with exit code {e.returncode}.\n"
        error_message += f"Command: {' '.join(e.cmd)}\n"
        error_message += f"Stderr: {e.stderr}"
        log.error(error_message)
        raise RuntimeError(error_message) # Re-raise with the detailed message
    except FileNotFoundError as e:
        log.error(f"FileNotFoundError: Error converting file '{filepath}' layer: '{layer}' to GeoPackage: {e}")
        raise RuntimeError(f"FileNotFoundError converting file '{filepath}' layer: '{layer}' to GeoPackage: {e}")
    except Exception as e:
        log.error(f"Unexpected error converting file '{filepath}' layer: '{layer}' to GeoPackage: {e}", exc_info=True)
        raise


def to_geojson(filepath: pathlib.Path, layer: str, catalogue_name: str = '', export_method: str = '') -> dict:
    """Converts a GIS file to the GeoJSON format.

    Args:
        filepath (pathlib.Path): Path to the file to be converted.
        layer (str): Layer to be converted.

    Returns:
        pathlib.Path: Path to the converted GeoJSON file.
    """
    log.info(f"Converting file '{filepath}' layer: '{layer}' to GeoJSON...")

    try:
        # Decompress and Flatten if Required
        filepath = compression.decompress(filepath)
        filepath = compression.flatten(filepath)

        # Construct Output Filepath
        output_dir = tempfile.mkdtemp()
        output_filepath = pathlib.Path(output_dir) / f"{layer}.geojson"

        command = [
            "ogr2ogr",
            "-unsetFid",
            str(output_filepath),
            str(filepath),
            str(layer),
        ]
        log.info(f"Running command: [{' '.join(command)}]")

        # Run the command
        subprocess.check_call(  # noqa: S603,S607
            command,
            timeout=1800,  # 30min
        )
        log.info(f"Success: Converted file: [{filepath}], layer: [{layer}] to GeoJSON successfully.")

        converted = {"uncompressed_filepath": output_filepath.parent, "full_filepath": output_filepath,  "orignal_filepath": filepath}
        log.info(f'converted: [{converted}]')

        return converted

    except subprocess.TimeoutExpired as e:
        log.error(f"The command has reached a timeout.  Error converting file '{filepath}' layer: '{layer}' to GeoJSON: {e}")
        raise RuntimeError(f"Error converting file '{filepath}' layer: '{layer}' to GeoJSON")
    except subprocess.CalledProcessError as e:
        log.error(f"Error converting file '{filepath}' layer: '{layer}' to GeoJSON: {e}")
        raise RuntimeError(f"Error converting file '{filepath}' layer: '{layer}' to GeoJSON")
    except FileNotFoundError as e:
        log.error(f"FileNotFoundError: Error converting file '{filepath}' layer: '{layer}' to GeoJSON: {e}")
        raise RuntimeError(f"FileNotFoundError converting file '{filepath}' layer: '{layer}' to GeoJSON: {e}")
    except Exception as e:
        log.error(f"Unexpected error converting file '{filepath}' layer: '{layer}' to GeoJSON: {e}")
        raise


def to_shapefile(filepath: pathlib.Path, layer: str, catalogue_name: str, export_method: str) -> dict:
    """Converts a GIS file to the ShapeFile format.

    Args:
        filepath (pathlib.Path): Path to the file to be converted.
        layer (str): Layer to be converted.

    Returns:
        pathlib.Path: Path to the converted ShapeFile file.
    """
    log.info(f"Converting file '{filepath}' layer: '{layer}' to ShapeFile...")

    try:
        # Decompress and Flatten if Required
        filepath = compression.decompress(filepath)
        filepath = compression.flatten(filepath)

        # Construct Output Filepath
        # Here we double up on the `layer.shp` to ensure its in a directory
        output_dir = tempfile.mkdtemp()
        output_filepath = pathlib.Path(output_dir) / f"{layer}.shp"
        output_filepath.mkdir(parents=True, exist_ok=True)
        output_filepath = output_filepath / f"{layer}.shp"

        command = [
            "ogr2ogr",
            "-overwrite",
            "-unsetFid",
            str(output_filepath),
            str(filepath),        
            str(catalogue_name)
        ]
        log.info(f"Running command: [{' '.join(command)}]")

        # Run the command
        subprocess.check_call(command)
        log.info(f"Success: Converted file [{filepath}], layer: [{layer}] to Shapefile successfully.")

        # Compress!
        compressed_filepath = compression.compress(output_filepath.parent)
        converted = {"compressed_filepath" : compressed_filepath, "uncompressed_filepath": output_filepath.parent}
        log.info(f'converted: [{converted}]')

        return converted

    except subprocess.TimeoutExpired as e:
        log.error(f"The command has reached a 30-minute timeout.  Error converting file '{filepath}' layer: '{layer}' to Shapefile: {e}")
        raise RuntimeError(f"Error converting file '{filepath}' layer: '{layer}' to Shapefile")
    except subprocess.CalledProcessError as e:
        log.error(f"Error converting file '{filepath}' layer: '{layer}' to Shapefile: {e}")
        raise RuntimeError(f"Error converting file '{filepath}' layer: '{layer}' to Shapefile")
    except FileNotFoundError as e:
        log.error(f"FileNotFoundError: Error converting file '{filepath}' layer: '{layer}' to Shapefile: {e}")
        raise RuntimeError(f"FileNotFoundError converting file '{filepath}' layer: '{layer}' to Shapefile: {e}")
    except Exception as e:
        log.error(f"Unexpected error converting file '{filepath}' layer: '{layer}' to Shapefile: {e}")
        raise


def to_geodatabase(filepath: pathlib.Path, layer: str, catalogue_name: str, export_method: str) -> dict:
    """Converts a GIS file to the GeoDatabase format.

    Args:
        filepath (pathlib.Path): Path to the file to be converted.
        layer (str): Layer to be converted.

    Returns:
        pathlib.Path: Path to the converted GeoDatabase file.
    """
    log.info(f"Converting file '{filepath}' layer: '{layer}' to GeoDatabase...")

    try:
        # Decompress and Flatten if Required
        filepath = compression.decompress(filepath)
        filepath_before_flatten = filepath
        filepath = compression.flatten(filepath)

        # Construct Output Filepath
        # Here we double up on the `layer.gdb` to ensure its in a directory
        output_dir = tempfile.mkdtemp()
        output_filepath = pathlib.Path(output_dir) / f"{layer}.gdb"
        output_filepath.mkdir(parents=True, exist_ok=True)
        output_filepath = output_filepath / f"{layer}.gdb"

        # Construct the command
        command = [
            "ogr2ogr",
            "-update",
            "-overwrite",
            "-nln", 
            str(layer),
            str(output_filepath),
            str(filepath),
            str(layer)
        ]
        log.info(f"Running command: [{' '.join(command)}]")

        # Run the command
        subprocess.check_call(command)
        log.info(f"Success: Converted file [{filepath}], layer: [{layer}] to GeoDatabase successfully.")

        # Compress!
        compressed_filepath = compression.compress(output_filepath.parent)
        converted = {"compressed_filepath" : compressed_filepath, "uncompressed_filepath": output_filepath.parent, "orignal_filepath": filepath, "filepath_before_flatten": filepath_before_flatten}
        log.info(f'converted: [{converted}]')

        # Return
        return converted

    except subprocess.TimeoutExpired as e:
        log.error(f"The command has reached a 30-minute timeout. Error converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
        raise RuntimeError(f"Timeout error converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
    except subprocess.CalledProcessError as e:
        log.error(f"CalledProcessError: Error converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
        raise RuntimeError(f"CalledProcessError converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
    except FileNotFoundError as e:
        log.error(f"FileNotFoundError: Error converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
        raise RuntimeError(f"FileNotFoundError converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
    except Exception as e:
        log.error(f"Unexpected error converting file '{filepath}' layer: '{layer}' to GeoDatabase: {e}")
        raise


def postgres_to_shapefile(layer_name: str, hostname: str, username: str, password: str, database:  str, port: str, sqlquery: str) -> dict: 
    log.info(f"Converting custom query for the PostGIS to shapefile...")

    try:
        converted = {}
        output_dir = tempfile.mkdtemp()
        cleaned_sqlquery = sqlquery.replace('\n', ' ')

        command = [
            "pgsql2shp",
            "-f", layer_name,
            "-h", str(hostname),
            "-u", str(username),
            "-p", str(port),
            "-P", str(password),
            str(database),
            str(cleaned_sqlquery)
        ]
        log.info(f"Running command: [{' '.join(command)}]")

        try:
            subprocess.run(
                command,
                cwd=output_dir,
                check=True,          # Raise an exception for non-zero exit codes (like check_call)
                capture_output=True, # Capture stdout and stderr into the result object
                text=True            # Decode stdout/stderr from bytes to text
            )
        except subprocess.TimeoutExpired as exc:
            log.error(f"The command has reached a timeout after {exc.timeout} for layer {layer_name}.  Stdout before timeout: {exc.stdout}.  Stderr before timeout: {exc.stderr}.")
            raise RuntimeError(f"Timeout error converting custom query for the PostGIS to shapefile: {exc}")
        except subprocess.CalledProcessError as exc:
            EMPTY_RESULT_MESSAGES = (
                "returned no rows",
                "not determine table metadata",
                "empty table"
            )
            # Now we handle the expected error. Check if the error message indicates that no records were returned.
            if any(msg in exc.stderr for msg in EMPTY_RESULT_MESSAGES):
                log.warning(f"The query returned no records. No shapefile will be created. This is a valid outcome.  exc.stderr: [{exc.stderr}]")
                return None  # Return None to indicate success with no output
            else:
                log.error(f"An unexpected error occurred while running pgsql2shp.  exc.stderr: [{exc.stderr}]")
                return False  # Return False to indicate unexpected error (e.g., syntax error, connection failure)

        log.info(f"Success: Converted custom query for the PostGIS to shapefile successfully.")
        compressed_filepath = compression.compress(pathlib.Path(output_dir))
        converted["output_dir"] = output_dir
        converted["compressed_filepath"] = str(compressed_filepath)
        log.info(f'converted: [{converted}]')

        return converted 

    except FileNotFoundError as e:
        log.error(f"FileNotFoundError: Error converting custom query for the PostGIS to shapefile: {e}")
        raise RuntimeError(f"FileNotFoundError converting custom query for the PostGIS to shapefile: {e}")
    except Exception as e:
        log.error(f"Unexpected error converting custom query for the PostGIS to shapefile: {e}")
        raise


def convert_tiff_to_geopackage(input_tiff, output_gpkg, output_layer_name):
    """
    Converts a TIFF file to a GeoPackage file.

    Parameters:
    input_tiff (str): Path to the input TIFF file.
    output_gpkg (str): Path to the output GeoPackage file.
    output_layer_name (str): Name of the layer to be added in the GeoPackage.

    """
    log.info(f"Converting tiff file: [{input_tiff}] to GeoDatabase...")

    try:
        # Open the input TIFF file
        tiff_dataset = gdal.Open(input_tiff)
        
        if tiff_dataset is None:
            raise ValueError("Failed to open the input TIFF file.")

        # Get the GeoPackage driver
        gpkg_driver = gdal.GetDriverByName("GPKG")
        
        if gpkg_driver is None:
            log.error("GeoPackage driver is not available.")
            raise ValueError("GeoPackage driver is not available.")

        # Create the GeoPackage file
        gpkg_dataset = gpkg_driver.Create(output_gpkg,
                                        tiff_dataset.RasterXSize,
                                        tiff_dataset.RasterYSize,
                                        tiff_dataset.RasterCount,
                                        gdal.GDT_Byte)
        
        if gpkg_dataset is None:
            log.error("Failed to create the GeoPackage file.")
            raise ValueError("Failed to create the GeoPackage file.")

        # Copy data from the TIFF file to the GeoPackage file
        for band_number in range(1, tiff_dataset.RasterCount + 1):
            band = tiff_dataset.GetRasterBand(band_number)
            gpkg_band = gpkg_dataset.GetRasterBand(band_number)
            gpkg_band.WriteArray(band.ReadAsArray())

        # Set the layer name in the GeoPackage file
        gpkg_dataset.SetMetadataItem("LAYERS", output_layer_name)

        # Close the GeoPackage file
        gpkg_dataset = None

        log.info(f'Success: Converted tiff file: [{input_tiff}] to GeoPackage successfully.')

    except ValueError as e:
        log.error(f"ValueError: {e}")
        raise
    except RuntimeError as e:
        log.error(f"RuntimeError: {e}")
        raise
    except Exception as e:
        log.error(f"Unexpected error converting tiff file '{input_tiff}' to GeoPackage: {e}")
        raise