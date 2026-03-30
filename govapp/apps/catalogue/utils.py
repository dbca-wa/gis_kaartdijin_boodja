"""Kaartdijin Boodja Catalogue Django Application Utility Functions."""


# Standard
import hashlib
import json
import logging

# Third Party
from functools import wraps
import pathlib
from rest_framework import status
from rest_framework import response
from rest_framework.serializers import ValidationError
from osgeo import osr

# Typing
from typing import Any, Iterable, Optional



# Logging
log = logging.getLogger(__name__)

def attributes_hash(attributes: Optional[Iterable[Any]]) -> str:
    """Calculates the hash of attributes.

    This function heavily relies on Python duck-typing - i.e., you can call
    this function with an iterable of *any* object, and the function will
    attempt to make it work. This was done so that Django models and
    dataclasses can both be passed in.

    This function is used to determine whether the Catalogue Entry matches its
    active Layer Submission at runtime.

    Args:
        attributes (Optional[Iterable[Any]]): Possible iterable of attributes.

    Returns:
        str: The hex SHA256 hash of the attributes.
    """
    # Initialise Hash
    hash = hashlib.sha256()  # noqa: A001

    # Allow the iteration below in the case that there are no attributes
    attributes = attributes or []

    # Loop through attributes in order
    # We expect the attributes to have an `order` field
    # If not, we leave them sorted as is
    for attribute in sorted(attributes, key=lambda a: getattr(a, "order", 0)):
        # Construct attribute dictionary
        attr = {
            "name": getattr(attribute, "name", None),
            "type": getattr(attribute, "type", None),
            "order": getattr(attribute, "order", None),
        }

        # Serialize attribute dictionary to JSON and encode the JSON
        json_string = json.dumps(attr, sort_keys=True, default=str)
        json_bytes = json_string.encode("UTF-8")

        # Update Hash
        hash.update(json_bytes)
    
    log.info(f'Hash calculated: [{hash.hexdigest()}] for the attributes: [{attributes}].')

    # Return
    return hash.hexdigest()


def find_enum_by_value(enum, value):
        for name, member in enum.__members__.items():
            if member.value == value:
                return member
        raise ValueError('No enum member found with value: {}'.format(value))


def validate_request(serializer_class, data):
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        raise ValidationError(serializer.errors)
    return serializer.validated_data


def view_error_handler(view_func):
    @wraps(view_func)
    def _wrapped_view(view_set, request, pk=None):
        try:
            return view_func(view_set, request, pk)
        except (ValueError, ValidationError) as e:
            return response.Response({'error_msg':e}, content_type='application/json', 
                                    status=status.HTTP_400_BAD_REQUEST)
    return _wrapped_view


def validation_error_hander(serializer_class):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(view_set, request, pk=None):
            validate_request(serializer_class, request.data)
            return view_func(view_set, request, pk)
        return _wrapped_view
    return decorator


def get_first_part_of_filename(filepath: pathlib.Path) -> str:
    filename = filepath.name
    parts = filename.split('.')
    first_part = parts[0]
    return first_part


def retrieve_additional_data(dataset):
    metadata_dict = {}

    # Get the metadata
    metadata = dataset.GetMetadata()

    for key, value in metadata.items():
        metadata_dict[key] = value

    # Resolution information
    x_resolution = dataset.GetGeoTransform()[1]  # X Resolution
    y_resolution = dataset.GetGeoTransform()[5]  # Y Resolution (often negative values)
    metadata_dict['X Resolution'] = x_resolution
    metadata_dict['Y Resolution'] = y_resolution

    # Get the number of bands
    bands = dataset.RasterCount
    metadata_dict['Number of bands'] = bands

    # Example of obtaining metadata for each band
    for i in range(1, bands + 1):
        band = dataset.GetRasterBand(i)
        band_metadata = band.GetMetadata()
        for key, value in band_metadata.items():
            metadata_dict[f'Band {i} {key}'] = value

    # Get the projection information
    projection = dataset.GetProjection()
    if not projection:
        dataset = None
        msg = 'File has no SRS information.  Processing cannot continue.'
        log.error(msg)
        raise ValueError(msg)
    
    metadata_dict['Projection'] = projection

    # Corner coordinates (e.g., geographic coordinates of the upper left corner)
    geo_transform = dataset.GetGeoTransform()
    origin_x = geo_transform[0]
    origin_y = geo_transform[3]
    metadata_dict['Origin'] = (origin_x, origin_y)

    return metadata_dict


def extract_epsg_from_wkt(wkt: str) -> Optional[str]:
    """Extracts the EPSG authority code from a WKT projection string.

    Args:
        wkt (str): WKT projection string.

    Returns:
        Optional[str]: EPSG string e.g. 'EPSG:7844', or None if not determinable.
    """
    if not wkt:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    authority = srs.GetAuthorityName(None)
    code = srs.GetAuthorityCode(None)
    if authority and code:
        return f"{authority}:{code}"
    return None
