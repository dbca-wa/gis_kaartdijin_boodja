"""GIS Compression Utilities."""


# Standard
import logging
import pathlib
import tarfile
import zipfile

# Third-Party
import py7zr
import rarfile


# Logging
log = logging.getLogger(__name__)


def decompress(file: pathlib.Path) -> pathlib.Path:
    """Decompresses a file and flattens it if required.

    Args:
        file (pathlib.Path): File to be decompressed.

    Returns:
        pathlib.Path: Path to the decompressed directory.
    """
    # Log
    log.info(f"Attemping to decompress '{file}' if required")

    # Check file
    if zipfile.is_zipfile(file):
        # `.zip`
        algorithm = zipfile.ZipFile

    elif tarfile.is_tarfile(file):
        # `.tar`
        algorithm = tarfile.TarFile  # type: ignore

    elif rarfile.is_rarfile(file):
        # `.rar`
        algorithm = rarfile.RarFile

    elif py7zr.is_7zfile(file):
        # `.7z`
        algorithm = py7zr.SevenZipFile  # type: ignore

    else:
        # None!
        algorithm = None

    # Check
    if not algorithm:
        # Log
        log.info("No compression detected, leaving unchanged")

        # Return the file unchanged
        return file

    # Construct Path for Extraction
    extracted_path = file.with_name(f"extracted_{file.stem}")

    # Log
    log.info(f"Detected compression '{algorithm}'")
    log.info(f"Decompressing '{file}' -> '{extracted_path}'")

    # Decompress
    with algorithm(file) as archive:
        # Extract
        archive.extractall(path=extracted_path)

    # Return
    return extracted_path


def flatten(path: pathlib.Path) -> pathlib.Path:
    """Flattens a directory.

    Args:
        path (pathlib.Path): Directory to be flattened.

    Returns:
        pathlib.Path: Flattened directory.
    """
    # Log
    log.info(f"Attemping to flatten '{path}' if required")

    # Enumerate subdirectories
    subdirs = [p for p in path.glob("*") if p.is_dir()]

    # Check if there is a single directory inside
    if len(subdirs) == 1:
        # Log
        log.info(f"Flattened '{path}' -> {subdirs[0]}")

        # Recurse, flatten that directory also if applicable and return
        return flatten(subdirs[0])

    # Log
    log.info("No flattening required, leaving unchanged")

    # Return
    return path
