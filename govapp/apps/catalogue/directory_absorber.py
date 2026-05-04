"""Kaartdijin Boodja Catalogue Django Application Absorber."""

# Standard
import datetime
import logging
import pathlib
import os
from typing import Optional
import uuid
import zipfile

# Third-Party
from django import conf
from django.db import transaction
import py7zr
import pytz
from osgeo import gdal, osr

# Local
from govapp.common import local_storage
from govapp.gis import compression, readers
from govapp.gis.conversions import to_geojson
from govapp.apps.catalogue import models
from govapp.apps.catalogue import directory_notifications
from govapp.apps.catalogue import utils
from govapp.gis.readers import types
from govapp.apps.logs import utils as logs_utils

# Logging
logger = logging.getLogger(__name__)


class Absorber:
    """Absorbs new layers into the system."""

    def __init__(self) -> None:
        """Instantiates the Absorber."""
        # Storage
        self.storage = local_storage.LocalStorage()
        self.ext_not_convert_to_geojson = ['.tif', '.tiff',]

    def absorb(self, path: str) -> None:
        """Absorbs new layers into the system.

        Args:
            path (str): File to absorb.
        """
        logger.info(f"Retrieving '[{path}]' from storage...")        

        # # Retrieve file from remote storage
        # # This retrieves and writes the file to our own temporary filesystem
        filepath = self.storage.get_path(path)        
        filepath = pathlib.Path(filepath)
        logger.info(f"Retrieved [{path}] to [{filepath}]")

        # Move the file on the remote storage into the archive area
        # The file is renamed to include a UTC timestamp, to avoid collisions
        import pytz
        timestamp = datetime.datetime.now(pytz.utc)
        timestamp_str = timestamp.strftime("%Y%m%dT%H%M%S")
        storage_directory = os.path.join(self.storage.get_data_storage_path(), f'{timestamp.year}')
        if not os.path.exists(storage_directory):
            os.makedirs(storage_directory)
            logger.info(f"Directory created: [{storage_directory}]")

        storage_path = os.path.join(storage_directory, filepath.stem + "." + timestamp_str + filepath.suffix)
        archive = self.storage.move_to_storage(filepath, storage_path)  # Move file to archive

        # # Log
        if archive:
            logger.info(f"Archived successfully: [{filepath}] to [{storage_path}]")
        else:
            logger.error(f"Archive failed: [{filepath}] to [{storage_path}]")

        self.process_file(storage_path)
        
    def process_file(self, path_to_file):
        """
        Extracts .7z or .zip files to a temp folder and executes get_gis_layers_from_file() on each extracted file.
        For .tiff or .tif files, executes get_gis_layers_from_file() directly.
        """
        # Get the directory containing the archive file
        folder_path = os.path.dirname(path_to_file)
        
        # Create a folder with the same name as the archive file (without extension)
        folder_name = os.path.splitext(os.path.basename(path_to_file))[0]
        temp_dir = os.path.join(folder_path, folder_name)

        try:
            filepaths_to_process = []

            compressed_algorithm = compression.get_compressed_algorithm(path_to_file)
            if compressed_algorithm:
                logger.info(f'Compressed algorithm detected: [{compressed_algorithm}] for the file: [{path_to_file}]')
                # Decompress the file into the temp folder
                with compressed_algorithm(path_to_file) as archive:
                    os.makedirs(temp_dir, exist_ok=True)
                    logger.info(f'Directory: [{temp_dir}] has been made for extract the file: [{path_to_file}]')

                    try:
                        archive.extractall(path=temp_dir)
                        logger.info(f'The file: [{path_to_file}] has been extracted into the folder: [{temp_dir}]')
                    except OSError as e:
                        import errno as _errno
                        extracted_files = os.listdir(temp_dir) if os.path.isdir(temp_dir) else []
                        logger.warning(
                            f'OSError during extractall for [{path_to_file}]: '
                            f'errno={e.errno} ({_errno.errorcode.get(e.errno, "UNKNOWN")}), '
                            f'strerror="{e.strerror}", '
                            f'filename="{e.filename}", '
                            f'extracted_file_count={len(extracted_files)}, '
                            f'extracted_files={extracted_files}'
                        )
                        if e.errno == _errno.EPERM and extracted_files:
                            # py7zr attempts to restore UID/GID on extracted directories (os.lchown),
                            # which fails with EPERM in non-root containers. The files themselves
                            # have been extracted successfully, so we can safely continue.
                            logger.warning(
                                f'File attribute restoration failed (EPERM) for [{path_to_file}], '
                                f'but files were extracted successfully. Continuing.'
                            )
                        else:
                            logger.error(
                                f'Unrecoverable OSError during extractall for [{path_to_file}]. '
                                f'extracted_file_count={len(extracted_files)}',
                                exc_info=True
                            )
                            raise

                # If extracted, loop through extracted files
                for extracted_filepath in os.listdir(temp_dir):
                    filepaths_to_process.append(os.path.join(temp_dir, extracted_filepath))
            else:
                logger.info(f'No compressed algorithm detected for the file: [{path_to_file}].')
                filepaths_to_process.append(path_to_file)

            # for filepath in filepaths_to_process:
            #     if filepath.lower().endswith(('.tiff', '.tif')):
            #         self.process_tiff_file(filepath)
            #     else:
            #         self.process_vector_file(filepath)
            tiff_exists = any(pathlib.Path(path).suffix.lower() in ['.tif', '.tiff',] for path in filepaths_to_process)
            geojson_exists = any(pathlib.Path(path).suffix.lower() in ['.json', '.geojson',] for path in filepaths_to_process)
            gpkg_exists = any(pathlib.Path(path).suffix.lower() in ['.gpkg', '.geopackage',] for path in filepaths_to_process)

            # Process all the files
            if tiff_exists or geojson_exists or gpkg_exists:
                logger.info(f'.tiff/.geojson file(s) detected')
                for filepath in filepaths_to_process:
                    if filepath.lower().endswith(('.tiff', '.tif')):
                        self.process_tiff_file(filepath)
                    elif filepath.lower().endswith(('.json', '.geojson')):
                        self.process_vector_file(filepath)
                    elif filepath.lower().endswith(('.gpkg', '.geopackage')):
                        self.process_vector_file(filepath)
                    else:
                        logger.warning(f"Unsupported file type for processing: [{filepath}].  Skipping.")
            else:
                # Call the original function for other file types
                self.process_vector_file(path_to_file)  # For compressed shapefile, compressed gdb file

        finally:
            pass

    def process_tiff_file(self, filepath):
        pathlib_filepath = pathlib.Path(filepath)
        logger.info(f'Processing tiff file: [{pathlib_filepath}]')
        
        result = {'total': 1, 'success':[], 'fail':[]}
        # Create CatalogueEntry
        try:
            self.absorb_tiff_as_layer(pathlib_filepath)
            result['success'].append(pathlib_filepath.name)
        except Exception as exc:
            result['fail'].append(f"layer:{pathlib_filepath.name}, exception:{exc}")
            # Log and continue
            logger.error(f"Error absorbing tiff as a layer:'{pathlib_filepath.name}': file:'{filepath}'", exc_info=exc)

        logger.info(f"End of absorbing layers from '{filepath}' :  fail:{len(result['fail'])} success:{len(result['success'])} total:{result['total']}")
        logger.info(f" - Succeed layers : {result['success']}\n - Failed layers : {result['fail']}")

    def absorb_tiff_as_layer(self, pathlib_filepath):
        # Open the file with GDAL
        dataset = gdal.Open(str(pathlib_filepath))
        if dataset is None:
            logger.error(f'Failed to open the file: {str(pathlib_filepath)}')
            return

        additional_data = utils.retrieve_additional_data(dataset)
        if self.is_projcs_unknown(additional_data['Projection']):
            logger.warning(f"SRS for file '{str(pathlib_filepath)}' is identified as 'unknown'.  This indicates the file lacks a standard EPSG identifier.")

        crs = utils.extract_epsg_from_wkt(additional_data.get('Projection', ''))
        logger.info(f"CRS detected for file '{str(pathlib_filepath)}': [{crs}]")

        metadata = types.Metadata(
            name=utils.get_first_part_of_filename(pathlib_filepath),  # filename is like: State_Map_Base_FMS.20240606T015418.tif
            description="",  # Blank by Default
            created_at=datetime.datetime.now(datetime.timezone.utc),
            additional_data=additional_data,
        )

        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.filter(name=metadata.name).first()

        # Check existing catalogue entry
        if not catalogue_entry:
            self.create_catalogue_entry(metadata, str(pathlib_filepath), crs=crs)
        else:
            self.update_catalogue_entry(catalogue_entry, metadata, str(pathlib_filepath), crs=crs)
        
        # Clean up GDAL dataset
        dataset = None

    def is_projcs_unknown(self, wkt_string: str) -> bool:
        """
        Checks if the PROJCS name in a WKT string is 'unknown'.

        :param wkt_string: The WKT string to check.
        :return: True if the PROJCS name is 'unknown', False otherwise.
                Returns False if the string is not a valid PROJCS.
        """
        if not wkt_string:
            return False
            
        srs = osr.SpatialReference()
        # ImportFromWkt can fail on invalid WKT, but GetAttrValue will just return None
        srs.ImportFromWkt(wkt_string)
        
        # Get the name of the PROJCS node (the first attribute, index 0)
        projcs_name = srs.GetAttrValue('PROJCS', 0)
        
        # Check if the name was found and if it is 'unknown' (case-insensitive)
        if projcs_name and projcs_name.lower() == 'unknown':
            return True
            
        return False

    def process_vector_file(self, filepath):
        pathlib_filepath = pathlib.Path(filepath)
        logger.info(f'Processing vector file: [{pathlib_filepath}]')

        reader = readers.reader.FileReader(pathlib_filepath)

        result = {'total':reader.layer_count(), 'success':[], 'fail':[]}
        # Create catalogue entries by looping through the layers
        for layer in reader.layers():
            logger.info(f"Absorbing layer '{layer.name}' from '{filepath}'")

            try:
                # Absorb layer
                self.absorb_vector_layer(layer, filepath)
                result['success'].append(layer.name)
            except Exception as exc:
                result['fail'].append(f"layer:{layer.name}, exception:{exc}")
                # Log and continue
                logger.error(f"Error absorbing layer:'{layer.name}': file:'{filepath}'", exc_info=exc)

            logger.info(f"Processing.. fail:{len(result['fail'])} success:{len(result['success'])} total:{result['total']}")

        logger.info(f"End of absorbing layers from '{filepath}' :  fail:{len(result['fail'])} success:{len(result['success'])} total:{result['total']}")
        logger.info(f" - Succeed layers : {result['success']}\n - Failed layers : {result['fail']}")

    def absorb_vector_layer(self, layer: readers.base.LayerReader, archive: str) -> None:
        """Absorbs a layer into the system.

        Args:
            layer (readers.base.LayerReader): Layer to absorb.
            archive (str): URL to the archived file for this layer.
        """
        # Log
        logger.info(f"Extracting data from layer: '{layer.name}'")

        # Extract metadata, attributes and symbology
        metadata = layer.metadata()
        attributes = layer.attributes()
        symbology = layer.symbology()

        logger.info(f"Extracting data from layer: '{attributes}'")
        # Retrieve existing catalogue entry from the database
        # Here we specifically check the Layer Metadata name
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.filter(name=metadata.name).first()

        # Extract CRS from the OGR layer
        crs = self._extract_crs_from_ogr_layer(layer.layer)
        logger.info(f"CRS detected for layer '{layer.name}': [{crs}]")

        # Check existing catalogue entry
        if not catalogue_entry:
            self.create_catalogue_entry(metadata, archive, attributes, symbology, crs=crs)
        else:
            self.update_catalogue_entry(catalogue_entry, metadata, archive, attributes, symbology, crs=crs)

    def _extract_crs_from_ogr_layer(self, ogr_layer) -> Optional[str]:
        """Extracts the EPSG CRS string from an OGR layer's spatial reference.

        Args:
            ogr_layer: An osgeo.ogr.Layer object.

        Returns:
            Optional[str]: e.g. 'EPSG:7844', or None if not determinable.
        """
        try:
            spatial_ref = ogr_layer.GetSpatialRef()
            if spatial_ref is None:
                return None
            wkt = spatial_ref.ExportToWkt()
            return utils.extract_epsg_from_wkt(wkt)
        except Exception as exc:
            logger.warning(f"Could not extract CRS from OGR layer: {exc}")
            return None

    @transaction.atomic()
    def create_catalogue_entry(
        self,
        metadata: readers.types.Metadata,
        archive: str,
        attributes: Optional[list[readers.types.Attribute]] = [],
        symbology: Optional[readers.types.Symbology] = None,
        crs: Optional[str] = None,
    ) -> bool:
        """Creates a new catalogue entry with the supplied values.

        Args:
            metadata (Metadata): Metadata for the entry.
            archive (str): Archive URL for the entry
            attributes (list[Attribute]): Attributes for the entry.
            symbology (Symbology): Symbology for the entry.

        Returns:
            bool: Whether the creation was successful.
        """
        # Log
        logger.info(f"Creating a new CatalogueEntry with the name: [{metadata.name}]...")
        
        # Calculate attributes hash
        attributes_hash = utils.attributes_hash(attributes)

        attributes_str = ""
        for attr in attributes:
            attributes_str = attributes_str+str(attr)+"\n"

        # Create Catalogue Entry
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.create(
            name=metadata.name,
            description=metadata.description,
        )
        logger.info(f'New CatalogueEntry: [{catalogue_entry}] has been created.')
        logs_utils.add_to_actions_log(
            user=None,
            model= catalogue_entry,
            action=f"CatalogueEntry: [{catalogue_entry}] has been created.",
            default_to_system=True
        )

        # Convert to a Geojson text
        extension = pathlib.Path(archive).suffix.lower()
        geojson_path = '' if extension in self.ext_not_convert_to_geojson else self.convert_to_geojson(archive, catalogue_entry)

        # Create Layer Submission
        self.create_layer_submission(metadata, archive, attributes_hash, attributes_str, catalogue_entry, geojson_path, True, crs=crs)

        # Create Layer Metadata
        self.create_or_update_layer_metadata(metadata, catalogue_entry)

        # Loop through attributes
        if attributes:
            self.create_layer_attributes(attributes, catalogue_entry)

        # Create Layer Symbology
        if symbology:
            self.create_layer_symbology(symbology, catalogue_entry)

        # Notify!
        directory_notifications.catalogue_entry_creation(catalogue_entry)

        # Return
        return True

    @transaction.atomic()
    def update_catalogue_entry(
        self,
        catalogue_entry: models.catalogue_entries.CatalogueEntry,
        metadata: readers.types.Metadata,
        archive: str,
        attributes: Optional[list[readers.types.Attribute]] = [],
        symbology: Optional[readers.types.Symbology] = None,
        crs: Optional[str] = None,
    ) -> bool:
        """Update a existing catalogue entry with the supplied values.

        Args:
            catalogue_entry (CatalogueEntry): Catalogue entry to update.
            metadata (Metadata): Metadata for the entry.
            archive (str): Archive URL for the entry.
            attributes (list[Attribute]): Attributes for the entry.
            symbology (Symbology): Symbology for the entry.

        Returns:
            bool: Whether the update was successful.
        """
        # Log
        logger.info(f"Updating existing catalogue entry: [{catalogue_entry}]...")
        
        # Calculate Layer Submission Attributes Hash
        attributes_hash = utils.attributes_hash(attributes)
        
        attributes_str = ""
        for attr in attributes:
            attributes_str = attributes_str+str(attr)+"\n"

        # Convert to a Geojson text
        extension = pathlib.Path(archive).suffix.lower()
        geojson_path = '' if extension in self.ext_not_convert_to_geojson else self.convert_to_geojson(archive, catalogue_entry)

        # Create New Layer Submission
        layer_submission = self.create_layer_submission(metadata, archive, attributes_hash, attributes_str, catalogue_entry, geojson_path, False, crs=crs)

        # CRS validation: if the catalogue has a configured default_crs and the file's
        # CRS is known but does not match, decline the submission immediately.
        if catalogue_entry.default_crs and crs and catalogue_entry.default_crs.epsg_code != crs:
            logger.warning(
                f"CRS mismatch for CatalogueEntry [{catalogue_entry}]: "
                f"expected '{catalogue_entry.default_crs.epsg_code}', got '{crs}'. Declining submission."
            )
            layer_submission.decline()
            directory_notifications.catalogue_entry_update_failure(catalogue_entry)
            return False
        
        # Create Layer Metadata
        self.create_or_update_layer_metadata(metadata, catalogue_entry)

        if catalogue_entry.type == models.catalogue_entries.CatalogueEntryType.SUBSCRIPTION_QUERY and not catalogue_entry.attributes.count():
            # When subscribing a custom query in PostGIS, only the catalogue_entry object is created initially,
            # and layer_attributes, layer_symbology, and layer_metadata need to be generated later here.

            # # Create Layer Metadata
            # self.create_layer_metadata(metadata, catalogue_entry)

            # Loop through attributes
            if attributes:
                self.create_layer_attributes(attributes, catalogue_entry)

            # Create Layer Symbology
            if symbology:
                self.create_layer_symbology(symbology, catalogue_entry)

        # Attempt to "Activate" this Layer Submission
        layer_submission.activate(False)
        
        # Check Success
        success = not layer_submission.is_declined()

        # Check Layer Submission
        if success:
            # Check for Publish Entry
            if hasattr(catalogue_entry, "publish_entry"):                
                # Publish
                catalogue_entry.publish_entry.publish()  # type: ignore[union-attr]

            # Notify!
            directory_notifications.catalogue_entry_update_success(catalogue_entry)

        else:
            # Send Update Failure Email
            directory_notifications.catalogue_entry_update_failure(catalogue_entry)
        # Return
        return success

    def create_layer_submission(self, metadata, archive, attributes_hash, attributes_str, catalogue_entry, geojson_path, is_active, crs: Optional[str] = None):
        file_size = None
        try:
            file_size = pathlib.Path(archive).stat().st_size
        except (OSError, ValueError):
            pass
        layer_submission = models.layer_submissions.LayerSubmission.objects.create(
            description=metadata.description,
            file=archive,
            file_size=file_size,
            is_active=is_active,  # Active!
            created_at=metadata.created_at,
            hash=attributes_hash,
            layer_attribute=attributes_str,
            catalogue_entry=catalogue_entry,
            geojson=geojson_path,
            crs=crs,
        )
        logger.info(f'LayerSubmission: [{layer_submission}] has been created for the CatalogueEntry: [{catalogue_entry}].')
        return layer_submission

    def create_or_update_layer_metadata(self, metadata, catalogue_entry):
        """
        Creates or retrieves a LayerMetadata object for the given CatalogueEntry.
        If the LayerMetadata object is created, it sets its created_at and additional_data fields.
        If the LayerMetadata object already exists and its additional_data is empty, it updates the additional_data field.
        """
        get_params = {
            'catalogue_entry': catalogue_entry
        }
        create_params = {
            'catalogue_entry': catalogue_entry,
            # 'created_at': metadata.created_at,
            'additional_data': metadata.additional_data
        }
        layer_metadata, created = models.layer_metadata.LayerMetadata.objects.get_or_create(defaults=create_params, **get_params)
        if created:
            # New LayerMetadata has been created
            logger.info(f'LayerMetadata: [{layer_metadata}] has been created for the CatalogueEntry: [{catalogue_entry}].')
        else:
            # Existing LayerMetadata found
            layer_metadata.additional_data = metadata.additional_data
            layer_metadata.save()
            logger.info(f'The LayerMetadata: [{layer_metadata}] for the CatalogueEntry: [{catalogue_entry}] has been updated by the additional_data: [{metadata.additional_data}].')

    def create_layer_attributes(self, attributes, catalogue_entry):
        existing_attributes = catalogue_entry.attributes.all()
        if existing_attributes.count():
            logger.warning(f'There are already existing LayerAttributes: [{catalogue_entry.attributes}] of the CatalogueEntry: [{catalogue_entry}].')
        else:
            for attribute in attributes:
                # Create Attribute
                layer_attribute = models.layer_attributes.LayerAttribute.objects.create(
                    name=attribute.name,
                    type=attribute.type,
                    order=attribute.order,
                    catalogue_entry=catalogue_entry,
                )
                logger.info(f'LayerMetadata: [{layer_attribute}] has been created for the CatalogueEntry: [{catalogue_entry}].')

    def create_layer_symbology(self, symbology, catalogue_entry):
        """
        Creates or retrieves a LayerSymbology object for the given CatalogueEntry.
        If the LayerSymbology object is created, it sets its sld field.
        If the LayerSymbology object already exists and its sld field is empty, it updates the sld field.
        """
        layer_symbology, created = models.layer_symbology.LayerSymbology.objects.get_or_create(
            catalogue_entry=catalogue_entry,
        )
        if created:
            layer_symbology.sld = symbology.sld
            layer_symbology.save()
            logger.info(f'LayerSymbology: [{layer_symbology}] has been created for the CatalogueEntry: [{catalogue_entry}].')
        else:
            if not layer_symbology.sld:
                layer_symbology.sld = symbology.sld
                layer_symbology.save()
                logger.info(f'The empty sld of the LayerSymbology: [{layer_symbology}] for the CatalogueEntry: [{catalogue_entry}] has been replaced by the sld: [{symbology.sld}].')
            else:
                logger.warning(f'The sld of the existing LayerSymbology: [{layer_symbology}] has a value, but an attempt was made to update it.')

    def convert_to_geojson(
        self, 
        filepath: str, 
        catalogue_entry: models.catalogue_entries.CatalogueEntry) -> pathlib.Path:
        # Convert to a Geojson file
        path_from = to_geojson(
            filepath=pathlib.Path(filepath),
            layer=catalogue_entry.name
        )
        return self.move_file_to_storage_with_uniquename(path_from['full_filepath'])

    def move_file_to_storage_with_uniquename(self, path_from:pathlib.Path):
        # Create a new folder hierarchically named to today's date(./yyyy/mm/dd) in the data storage when it dosen't exist
        # date_str = datetime.date.today().strftime("%d%m%Y")
        # data_storage_path = f"{self.storage.get_data_storage_path()}/geojson/{datetime.date.today().year}/{str(datetime.date.today().month).zfill(2)}/{datetime.date.today().day}"

        data_storage_path = os.path.join(
            self.storage.get_data_storage_path(),
            "geojson",
            str(datetime.date.today().year),
            str(datetime.date.today().month).zfill(2),
            str(datetime.date.today().day)
        )

        if not os.path.exists(data_storage_path):
            os.makedirs(data_storage_path)
        
        # Change the file name with uuid and join with the data storage path
        filename_to = f"{path_from.stem}_{str(uuid.uuid4())}{path_from.suffix}"
        path_to = os.path.join(data_storage_path, filename_to)

        # Move the file into a folder named date(ddmmyyyy) in the data storage
        if self.storage.move_to_storage(str(path_from), path_to):
            return path_to
        
        # Raise Exception when it failed for some reasons
        raise Exception(f"failed to move file from {path_from} to {path_to}")
