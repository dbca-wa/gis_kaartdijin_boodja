"""GeoServer Abstractions."""


# Standard
import json
import logging
import pathlib
import requests
import time
from django.template import loader

# Third-Party
from django import conf
import httpx

# Typing
from typing import Any, Optional
from django.template.loader import render_to_string

from govapp import settings
from govapp.common.utils import handle_http_exceptions
import xml.etree.ElementTree as ET # Import the XML parser

# Logging
log = logging.getLogger(__name__)


class GeoServer:
    """GeoServer Abstraction."""

    def __init__(
        self,
        service_url: str,
        username: str,
        password: str,
    ) -> None:
        """Instantiates the GeoServer Abstraction.

        Args:
            service_url (str): URL to the GeoServer service.
            username (str): Username for the GeoServer service.
            password (str): Password for the GeoServer service.
        """
        # Instance Attributes
        self.service_url = service_url
        self.username = username
        self.password = password

        # Strip Trailing Slash from Service URL
        self.service_url = self.service_url.rstrip("/")
    
    @property
    def auth(self):
        return (self.username, self.password)

    @property
    def headers_json(self):
        return {"content-type": "application/json","Accept": "application/json"}

    @handle_http_exceptions(log)
    def create_or_update_cached_layer(self, layer_name, service_type, create_cached_layer=True, expire_server_cache_after_n_seconds=0, expire_client_cache_after_n_seconds=0):
        from govapp.apps.catalogue.models.catalogue_entries import CatalogueEntryType

        # Construct URL
        url = f"{self.service_url}/gwc/rest/layers/{layer_name}.json"
        log.info(f'Creating/Updating the cached layer... url: [{url}]')
        
        template = loader.get_template('govapp/geoserver/gwc_layer_setting.xml')
        response = httpx.put(
            url=url,
            auth=(self.username, self.password),
            headers={'content-type':'text/xml'},
            data=template.render({
                'layer_name': layer_name,
                'service_type': service_type,
                'create_cached_layer': create_cached_layer,
                'expire_cache': expire_server_cache_after_n_seconds,
                'expire_clients': expire_client_cache_after_n_seconds,
                'CatalogueEntryType': CatalogueEntryType
            })
        )

        response.raise_for_status()

        if response.status_code == 201:
            log.info(f"Cached layer: [{layer_name}] created successfully in the geoserver: [{self.service_url}].")
        elif response.status_code == 200:
            log.info(f"Cached layer: [{layer_name}] updated successfully in the geoserver: [{self.service_url}].")
        else:
            log.error(f"Failed to create/update the cached layer: [{layer_name}] in the geoserver: [{self.service_url}].  {response.status_code} {response.text}")
        # Layer exists, proceed with deletion
    
    @handle_http_exceptions(log)
    def create_store_if_not_exists(self, workspace_name, store_name, data, datastore_type='datastores'):
        # URL to check the existence of the store
        store_get_url = f"{self.service_url}/rest/workspaces/{workspace_name}/{datastore_type}/{store_name}"
        log.info(f'store_get_url: {store_get_url}')

        # Check if Store Exists
        log.info(f'Checking if the store exists...')
        with httpx.Client(auth=(self.username, self.password)) as client:
            response = client.get(store_get_url, headers=self.headers_json)

        # data = data.replace('\n', '')
        # Decide whether to perform a POST or PUT request based on the existence of the store
        if response.status_code == 404: 
            # Store does not exist, perform a POST request
            url = f"{self.service_url}/rest/workspaces/{workspace_name}/{datastore_type}"

            log.info(f'Store: [{store_name}] does not exist. Performing POST request to create the store.')
            log.info(f'POST url: {url}')
            log.info(f'data: {data}')
            with httpx.Client(auth=(self.username, self.password)) as client:
                response = client.post(url=url, headers=self.headers_json, data=data)
        else:
            # Store exists, perform a PUT request
            log.info(f'Store: [{store_name}] exists. Performing PUT request to update the store.')
            log.info(f'PUT url: {store_get_url}')
            log.info(f'data: {data}')
            with httpx.Client(auth=(self.username, self.password)) as client:
                response = client.put(url=store_get_url, headers=self.headers_json, data=data)
            
        return response

    def _stream_file(self, filepath: pathlib.Path, chunk_size: int = 1024 * 1024):
        """Generator function to stream file in chunks.

        Args:
            filepath (pathlib.Path): Path to the file to stream.
            chunk_size (int): Size of chunks to read.

        Yields:
            Generator[bytes, None, None]: File chunks as bytes.
        """
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    
    def _update_gpkg_datastore_params(
        self,
        workspace: str,
        store_name: str,
        params_to_update: dict
    ) -> None:
        """
        Updates specific connection parameters for an existing GeoPackage datastore
        """
        if not params_to_update:
            log.info("No datastore parameters to update.")
            return

        log.info(f"Updating datastore [{store_name}] with parameters: [{params_to_update}]")
        datastore_url = f"{self.service_url}/rest/workspaces/{workspace}/datastores/{store_name}.json"

        try:
            with requests.Session() as session:
                session.auth = (self.username, self.password)
                headers = {'Content-type': 'application/json', 'Accept': 'application/json'}

                # Step 1: GET the current datastore configuration
                log.info("Fetching current datastore configuration...")
                get_response = session.get(datastore_url, headers=headers)
                get_response.raise_for_status()
                datastore_data = get_response.json()
                log.debug(f"Retrieved datastore configuration:\n{json.dumps(datastore_data, indent=2)}")

                # Step 2: Modify the connection parameters in the correct structure
                log.info("Modifying connection parameters...")
                connection_params = datastore_data.setdefault("dataStore", {}).setdefault("connectionParameters", {})
                entry_list = connection_params.setdefault("entry", [])

                # For each parameter we want to update...
                for key_to_update, value_to_update in params_to_update.items():
                    found_and_updated = False
                    # ...iterate through the existing entries...
                    for entry_item in entry_list:
                        # ...and if we find a matching key...
                        if entry_item.get("@key") == key_to_update:
                            # ...update its value and mark it as found.
                            entry_item["$"] = str(value_to_update)
                            found_and_updated = True
                            break # Move to the next parameter to update
                    
                    # If after checking all entries, we didn't find the key...
                    if not found_and_updated:
                        # ...it means we need to add a new entry to the list.
                        log.info(f"Key '{key_to_update}' not found, adding it as a new entry.")
                        entry_list.append({"@key": key_to_update, "$": str(value_to_update)})

                log.debug(f"Sending updated datastore configuration:\n{json.dumps(datastore_data, indent=2)}")

                # Step 3: PUT the updated configuration back to the server
                log.info("Sending updated configuration to GeoServer...")
                put_response = session.put(datastore_url, json=datastore_data, headers=headers)
                put_response.raise_for_status()
                log.info(f"Successfully updated datastore '{store_name}'.")

        except requests.exceptions.HTTPError as e:
            log.error(f"Failed to update datastore '{store_name}'. Status: {e.response.status_code}, Response: {e.response.text}")
            raise
        except (KeyError, TypeError) as e:
            log.error(f"Failed to parse datastore configuration for '{store_name}'. Structure might be unexpected. Details: {e}")
            raise

    @handle_http_exceptions(log)
    def upload_geopackage(
        self,
        workspace: str,
        layer: str,
        filepath: pathlib.Path,
        chunk_size: Optional[int] = 1024 * 1024,  # 1MB chunks by default
        memory_map_size: Optional[int] = None,
    ) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
            chunk_size (Optional[int]): Size of chunks for streaming upload (default: 1MB)
        """
        log.info(f"Uploading Geopackage '{filepath}' to GeoServer...")

        # Construct URL
        url = f"{self.service_url}/rest/workspaces/{workspace}/datastores/{layer}/file.gpkg"

        # Set appropriate headers for streaming upload
        headers = {
            'Content-Type': 'application/x-gpkg',  # GeoPackage mime type
            'Transfer-Encoding': 'chunked',
            'Connection': 'keep-alive'
        }
        
        # Set query parameters
        params = {
            'filename': filepath.name,
            'update': 'overwrite',
            'configure': 'all'
            # 'configure': 'none'
        }

        # Add the memory map size to the query parameters ONLY if it's provided.
        # if memory_map_size is not None:
        #     # The key for the query parameter is 'mmap'.
        #     params['mmap'] = str(memory_map_size)

        # Log file size for monitoring
        file_size = filepath.stat().st_size
        log.info(f"File size: {file_size / (1024*1024):.2f} MB")

        with requests.Session() as session:
            # Perform streaming upload
            try:
                response = session.put(
                    url=url,
                    data=self._stream_file(filepath, chunk_size),
                    params=params,
                    headers=headers,
                    auth=(self.username, self.password),
                    timeout=3000.0,  # 50 minutes timeout
                    stream=True
                )

                log.info(f"GeoServer response: '{response.status_code}: {response.text}'")
                response.raise_for_status()

                # --- START: NEW ASYNCHRONOUS TASK HANDLING ---
                if response.status_code == 202:
                    status_url = response.headers.get('Location')
                    if status_url:
                        log.info(f"GeoServer is processing the upload asynchronously. Polling status at: {status_url}")
                        
                        # Poll the status URL until the task is complete
                        max_wait_seconds = 180 # Wait for a maximum of 3 minutes
                        start_time = time.time()
                        while time.time() - start_time < max_wait_seconds:
                            try:
                                status_response = session.get(status_url, auth=(self.username, self.password))
                                status_response.raise_for_status()
                                status_data = status_response.json()
                                task_status = status_data.get('task', {}).get('state', 'PENDING').upper()

                                if task_status == 'FINISHED':
                                    log.info("GeoServer asynchronous processing finished successfully.")
                                    return # The task is complete
                                elif task_status in ['RUNNING', 'PENDING']:
                                    log.info(f"Task status: {task_status}. Waiting...")
                                    time.sleep(5) # Wait 5 seconds before polling again
                                else: # FAILED, ABORTED
                                    error_message = status_data.get('task', {}).get('error', {}).get('message', 'Unknown error')
                                    log.error(f"GeoServer task failed with status '{task_status}': {error_message}")
                                    raise RuntimeError(f"GeoServer task failed: {error_message}")

                            except requests.exceptions.RequestException as e:
                                log.error(f"Error polling task status: {e}")
                                time.sleep(5)
                        
                        # If the loop finishes without returning, it timed out
                        raise RuntimeError("GeoServer task timed out after waiting for 3 minutes.")
                    else:
                        log.warning("GeoServer returned 202 but no Location header. Waiting a fixed time.")
                        time.sleep(5) # Fallback delay
                        return
                # --- END: NEW ASYNCHRONOUS TASK HANDLING ---

            except requests.exceptions.RequestException as e:
                log.error(f'Upload failed: [{str(e)}]')
                raise

            # --- START: DATATORE CONFIGURATION UPDATE STEP ---
            # After the file upload (and async task) is successful,
            # explicitly update the datastore's connection parameters.
            if memory_map_size is not None:
                try:
                    # The connection parameter key for memory map size is "memory map size"
                    params_to_update = {"memory map size": str(memory_map_size)}
                    self._update_gpkg_datastore_params(workspace, layer, params_to_update)
                except Exception as e:
                    # Log a warning but don't fail the entire upload if only the config update fails
                    log.warning(f"File was uploaded successfully, but failed to update memory map size for store [{layer}]. Please check manually. Error: {e}")
            # --- END: DATATORE CONFIGURATION UPDATE STEP ---

    @handle_http_exceptions(log)
    def upload_tif(
        self,
        workspace: str,
        layer: str,
        filepath: pathlib.Path,
        chunk_size: Optional[int] = 1024 * 1024  # 1MB chunks by default
    ) -> None:
        """Uploads a GeoTIFF file. It forcefully attempts to clean up any pre-existing 
        resources (layer and store) before uploading, ignoring 404 errors on delete."""
        log.info(f"Preparing to upload GeoTiff '{filepath.name}' as resource '{layer}' in workspace '{workspace}'")

        # --- START: FORCEFUL PRE-FLIGHT CLEANUP ---
        # This approach attempts to delete both layer and store, ignoring 'Not Found' errors.
        # This is more robust against inconsistencies where GET might fail but the resource exists.
        try:
            with requests.Session() as session:
                session.auth = (self.username, self.password)

                # Define URLs for both the layer and the store
                # The layer name in the URL must be prefixed with the workspace
                layer_delete_url = f"{self.service_url}/rest/layers/{workspace}:{layer}"
                store_delete_url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{layer}?recurse=true"

                # Step 1: Attempt to delete the LAYER first.
                # An orphaned layer can prevent a store with the same name from being created.
                log.info(f"Attempting to delete layer (if it exists): {layer_delete_url}")
                layer_del_response = session.delete(layer_delete_url, timeout=(15, 120))
                if layer_del_response.status_code == 200:
                    log.info(f"Successfully deleted layer '{layer}'.")
                elif layer_del_response.status_code == 404:
                    log.info(f"Layer '{layer}' did not exist; no action needed.")
                else:
                    # If deletion fails for any other reason, raise an error.
                    layer_del_response.raise_for_status()

                # Step 2: Attempt to delete the COVERAGE STORE.
                # Using recurse=true is a good practice, though the layer might be gone already.
                log.info(f"Attempting to delete coverage store (if it exists): {store_delete_url}")
                store_del_response = session.delete(store_delete_url, timeout=(15, 120))
                if store_del_response.status_code == 200:
                    log.info(f"Successfully deleted coverage store '{layer}'.")
                elif store_del_response.status_code == 404:
                    log.info(f"Coverage store '{layer}' did not exist; no action needed.")
                else:
                    store_del_response.raise_for_status()
                
                log.info(f"Pre-flight cleanup complete for resource '{layer}'.")

        except requests.exceptions.RequestException as e:
            log.error(f"An error occurred during pre-flight cleanup for resource '{layer}': {e}")
            raise
        # --- END: FORCEFUL PRE-FLIGHT CLEANUP ---


        # --- UPLOAD LOGIC (This part remains the same) ---
        upload_url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{layer}/file.geotiff"
        headers = {'Content-Type': 'image/tiff'}
        params = {'filename': layer, 'configure': 'all'}
        file_size = filepath.stat().st_size
        log.info(f"File size: {file_size / (1024*1024):.2f} MB. Starting streaming upload...")

        # The rest of the function (the PUT request) remains identical to your current version.
        # ... (your existing try/except block for the PUT request) ...
        try:
            with requests.Session() as session:
                response = session.put(
                    url=upload_url,
                    data=self._stream_file(filepath, chunk_size),
                    params=params,
                    headers=headers,
                    auth=(self.username, self.password),
                    timeout=(15, 3000.0),
                    stream=True
                )
                log.info(f"GeoServer response: [{response.status_code}]: [{response.text}]")
                response.raise_for_status()
                log.info(f"Successfully uploaded GeoTIFF and created resource '{layer}'.")
        except requests.exceptions.HTTPError as e:
            log.error(
                f"HTTP Error during upload for store '{layer}'. "
                f"Status Code: {e.response.status_code}. Response: {e.response.text}"
            )
            raise
        except requests.exceptions.RequestException as e:
            log.error(f"An unexpected error occurred during upload for store '{layer}'. Details: {e}")
            raise

    def _build_file_url(
        self,
        file_path: pathlib.Path,
        geoserver_data_dir: Optional[pathlib.Path] = None,
    ) -> str:
        """Builds a GeoServer file URL for an external file reference.

        When ``geoserver_data_dir`` is provided and ``file_path`` is under it, returns a
        ``file:data/<relative>`` URL so that GeoServer resolves the path internally relative
        to its data directory.  This bypasses the GeoServer 2.23+ filesystem sandbox
        canonical-path check that rejects SMB/Azure File Share mounted paths.

        Otherwise falls back to an absolute ``file://<path>`` URL.
        """
        if geoserver_data_dir is not None:
            try:
                rel = file_path.relative_to(geoserver_data_dir)
                # GeoServer resolves "file:<rel>" relative to its data directory.
                # e.g. file_path=/opt/geoserver_data/data/ws/name/f.tif,
                # data_dir=/opt/geoserver_data → rel=data/ws/name/f.tif
                # → URL: file:data/ws/name/f.tif  ("data/" is the actual subdir name)
                return f"file:{rel}"
            except ValueError:
                log.warning(
                    f"File path '{file_path}' is not under geoserver_data_dir "
                    f"'{geoserver_data_dir}'; falling back to absolute file URL."
                )
        return f"file://{file_path}"

    @handle_http_exceptions(log)
    def configure_geopackage_from_path(
        self,
        workspace: str,
        layer: str,
        file_path_on_volume: pathlib.Path,
        memory_map_size: Optional[int] = None,
        geoserver_data_dir: Optional[pathlib.Path] = None,
    ) -> None:
        """Configures a GeoPackage datastore in GeoServer using a file already present on the
        shared Docker volume (no HTTP file upload).

        Uses GeoServer's external file reference API
        (PUT .../datastores/{store}/external.gpkg) which tells GeoServer to read the file
        directly from its local filesystem rather than receiving the file over HTTP.

        Args:
            workspace: GeoServer workspace name.
            layer: Datastore and layer name.
            file_path_on_volume: Absolute path to the .gpkg file as seen by GeoServer
                (i.e. the GeoServer-side mount path on the shared Docker volume).
            memory_map_size: Optional memory map size parameter for large GeoPackage files.
            geoserver_data_dir: GeoServer data directory root. When provided and the file
                is under this directory, uses ``file:data/<relative>`` URL format to bypass
                the GeoServer 2.23+ filesystem sandbox canonical-path check on SMB mounts.
        """
        log.info(
            f"Configuring GeoPackage store '{layer}' in workspace '{workspace}' "
            f"from volume path '{file_path_on_volume}'"
        )
        file_url = self._build_file_url(file_path_on_volume, geoserver_data_dir)
        log.info(f"Using file URL: '{file_url}'")
        url = (
            f"{self.service_url}/rest/workspaces/{workspace}"
            f"/datastores/{layer}/external.gpkg"
        )
        params = {"configure": "all", "update": "overwrite"}
        headers = {"Content-Type": "text/plain"}

        with requests.Session() as session:
            response = session.put(
                url=url,
                data=file_url,
                params=params,
                headers=headers,
                auth=(self.username, self.password),
                timeout=300.0,
            )
            log.info(f"GeoServer response: '{response.status_code}: {response.text}'")
            response.raise_for_status()

        if memory_map_size is not None:
            try:
                self._update_gpkg_datastore_params(workspace, layer, {"memory map size": str(memory_map_size)})
            except Exception as e:
                log.warning(
                    f"GeoPackage store configured from path, but failed to update memory map size "
                    f"for store '{layer}'. Please check manually. Error: {e}"
                )

    @handle_http_exceptions(log)
    def configure_geotiff_from_path(
        self,
        workspace: str,
        layer: str,
        file_path_on_volume: pathlib.Path,
        geoserver_data_dir: Optional[pathlib.Path] = None,
    ) -> None:
        """Configures a GeoTIFF coveragestore in GeoServer using a file already present on the
        shared Docker volume (no HTTP file upload).

        Mirrors the pre-flight cleanup logic from :meth:`upload_tif` so that any stale layer
        or coveragestore is removed before the new one is created, then uses GeoServer's
        external file reference API (PUT .../coveragestores/{store}/external.geotiff).

        Args:
            workspace: GeoServer workspace name.
            layer: Coveragestore and layer name.
            file_path_on_volume: Absolute path to the .tif file as seen by GeoServer
                (i.e. the GeoServer-side mount path on the shared Docker volume).
            geoserver_data_dir: GeoServer data directory root. When provided and the file
                is under this directory, uses ``file:data/<relative>`` URL format to bypass
                the GeoServer 2.23+ filesystem sandbox canonical-path check on SMB mounts.
        """
        log.info(
            f"Configuring GeoTIFF store '{layer}' in workspace '{workspace}' "
            f"from volume path '{file_path_on_volume}'"
        )

        # Pre-flight cleanup: delete any stale layer and coveragestore so that
        # creation of the new store is not blocked by an existing resource.
        layer_delete_url = f"{self.service_url}/rest/layers/{workspace}:{layer}"
        store_delete_url = (
            f"{self.service_url}/rest/workspaces/{workspace}"
            f"/coveragestores/{layer}?recurse=true"
        )

        try:
            with requests.Session() as session:
                session.auth = (self.username, self.password)

                log.info(f"Attempting to delete layer (if it exists): {layer_delete_url}")
                layer_del = session.delete(layer_delete_url, timeout=(15, 120))
                if layer_del.status_code == 200:
                    log.info(f"Deleted layer '{layer}'.")
                elif layer_del.status_code == 404:
                    log.info(f"Layer '{layer}' did not exist; nothing to delete.")
                else:
                    layer_del.raise_for_status()

                log.info(f"Attempting to delete coverage store (if it exists): {store_delete_url}")
                store_del = session.delete(store_delete_url, timeout=(15, 120))
                if store_del.status_code == 200:
                    log.info(f"Deleted coverage store '{layer}'.")
                elif store_del.status_code == 404:
                    log.info(f"Coverage store '{layer}' did not exist; nothing to delete.")
                else:
                    store_del.raise_for_status()

                log.info(f"Pre-flight cleanup complete for resource '{layer}'.")
        except requests.exceptions.RequestException as e:
            log.error(f"Pre-flight cleanup failed for resource '{layer}': {e}")
            raise

        # Configure the coveragestore using the catalog REST API (two-step: store then coverage).
        # We deliberately avoid the external.geotiff PUT endpoint because GeoServer 2.23+
        # runs a sandbox canonical-path check on the file URL inside that handler, which
        # rejects SMB / Azure File Share mounts even when the path is nominally correct.
        # The catalog API just writes the store configuration without touching the file.
        file_url = self._build_file_url(file_path_on_volume, geoserver_data_dir)
        log.info(f"Using file URL: '{file_url}'")

        # POST to the collection URL creates a new store.
        stores_url = (
            # Ref: https://docs.geoserver.org/stable/en/user/rest/api/coveragestores.html
            f"{self.service_url}/rest/workspaces/{workspace}/coveragestores.json"
        )
        coverage_url = (
            # Ref: https://docs.geoserver.org/stable/en/user/rest/api/coverages.html
            f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{layer}/coverages.json"
        )
        store_payload = {
            "coverageStore": {
                "name": layer,
                "type": "GeoTIFF",
                "enabled": True,
                "workspace": {"name": workspace},
                "url": file_url,
            }
        }
        # nativeName must match the GeoTIFF's internal coverage name, which GeoServer
        # derives from the filename stem (e.g. "Tiff-Test-20260319_15.20260319_155927...").
        native_name = file_path_on_volume.stem
        coverage_payload = {
            "coverage": {
                "name": layer,
                "nativeName": native_name,
            }
        }

        with requests.Session() as session:
            session.auth = (self.username, self.password)

            # Step 1: create the coverage store (just writes catalog config, no file I/O).
            log.info(f"Creating coverage store via catalog API: {stores_url}")
            resp_store = session.post(
                url=stores_url,
                json=store_payload,
                timeout=60.0,
            )
            log.info(f"Coverage store response: '{resp_store.status_code}: {resp_store.text}'")
            resp_store.raise_for_status()

            # Step 2: create the coverage (layer) from the store.
            log.info(f"Creating coverage (layer) via catalog API: {coverage_url}")
            resp_coverage = session.post(
                url=coverage_url,
                json=coverage_payload,
                timeout=60.0,
            )
            log.info(f"Coverage response: '{resp_coverage.status_code}: {resp_coverage.text}'")
            resp_coverage.raise_for_status()

    @handle_http_exceptions(log)
    def create_layer_from_coveragestore(self, workspace: str, layer: str) -> None:
        """
        Creates a layer in GeoServer from an existing coverage store.

        Args:
            workspace (str): Workspace where the coverage store exists.
            layer (str): Name of the layer to create in GeoServer.
        """
        try:
            response_data = self.get_layer_details(layer)
        except Exception as e:
            log.error(f'Failed to get layer details: [{layer}].  {str(e)}')
            raise
        response_data['layer']['resource']['srs'] = "EPSG:26918"
        response_data['layer']['resource']['boundingBox'] = {
                "nativeBoundingBox": {
                    "minx": -180,
                    "miny": -90,
                    "maxx": 180,
                    "maxy": 90,
                    "crs": "EPSG:26918"
                },
                "latLonBoundingBox": {
                    "minx": -180,
                    "miny": -90,
                    "maxx": 180,
                    "maxy": 90,
                    "crs": "EPSG:26918"
                }
            }
        log.info(f'layer_data: [{response_data}]')
        # Log
        log.info(f"Creating layer '{layer}' in workspace '{workspace}'")

        # Construct URL for layers endpoint
        layers_url = f"{self.service_url}/rest/layers/{workspace}:{layer}.json"

        # Perform POST request to create the layer
        response = httpx.put(
            url=layers_url,
            content=json.dumps(response_data),
            headers=self.headers_json,
            auth=(self.username, self.password),
            timeout=3000.0
        )

        # Log GeoServer response
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check response status
        response.raise_for_status()

    def upload_store_wms(self, workspace, store_name, context) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading WMS Store to GeoServer...")
        
        data = render_to_string('govapp/geoserver/wms/wms_store.json', context)

        response = self.create_store_if_not_exists(workspace, store_name, data, datastore_type='wmsstores')
        
        # Log
        log.info(f"GeoServer WMS response: '{response.status_code}: {response.text}'")
        
        # Check Response
        response.raise_for_status()

    @handle_http_exceptions(log)
    def upload_layer_wms(
            self,
            workspace,
            store_name,
            layer_name,
            context
        ) -> None:
            """Uploads a Geopackage file to the GeoServer.

            Args:
                workspace (str): Workspace to upload files to.
                layer (str): Name of the layer to upload GeoPackage for.
                filepath (pathlib.Path): Path to the Geopackage file to upload.
            """
            # Log
            log.info(f"Uploading WMS Layer to GeoServer...")
            
            xml_data = render_to_string('govapp/geoserver/wms/wms_layer.json', context)
            log.info(f'data: { xml_data }')

            layer_get_url = f"{self.service_url}/rest/workspaces/{workspace}/wmsstores/{store_name}/wmslayers/{layer_name}"
            log.info(f'layer_get_url: {layer_get_url}')

            # Check if Layer Exists
            log.info(f'Checking if the layer exists...')
            response = httpx.get(
                url=layer_get_url+"",
                auth=(self.username, self.password),
                headers=self.headers_json,
                timeout=120.0
            )

            log.info(f'Response of the check: { response.status_code }: { response.text }')

            if response.status_code == 200:
                log.info(f"Layer: {layer_name} exists.  Delete it...")
                response = httpx.delete(
                    url=layer_get_url+"?recurse=true",
                    auth=(self.username, self.password),
                    #data=xml_data,
                    headers=self.headers_json,
                    timeout=120.0
                )
            else:
                log.info(f'Layer: {layer_name} does not exist.')

            # Construct URL
            url = f"{self.service_url}/rest/workspaces/{workspace}/wmsstores/{store_name}/wmslayers/"

            log.info(f'Creat the layer by post request...')
            log.info(f'Post url: { url }')
            log.info(f'data: {xml_data}')
            response = httpx.post(
                url=url,
                auth=(self.username, self.password),
                data=xml_data,
                headers=self.headers_json,
                timeout=3000
            )

            log.info(f'Response of the create: { response.status_code }: { response.text }')
            
            # Check Response
            response.raise_for_status()        

    def upload_store_postgis(self, workspace, store_name, context) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading POSTGIS Store to GeoServer...")
        
        data = render_to_string('govapp/geoserver/postgis/postgis_store.json', context)
        # data_update = render_to_string('govapp/geoserver/postgis/postgis_store_update.json', context)

        response = self.create_store_if_not_exists(workspace, store_name, data)

        # Log
        log.info(f"GeoServer POSTGIS response: '{response.status_code}: {response.text}'")
        
        # Check Response
        response.raise_for_status()     

    def upload_store_wfs(self, workspace, store_name, context) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading WFS Store to GeoServer")
        
        data = render_to_string('govapp/geoserver/wfs/wfs_store.json', context)
        
        response = self.create_store_if_not_exists(workspace, store_name, data)
        
        # Log
        log.info(f"GeoServer WFS response: '{response.status_code}: {response.text}'")
        
        # Check Response
        response.raise_for_status()    

    @handle_http_exceptions(log)
    def upload_layer_wfs(
            self,
            workspace,
            store_name,
            layer_name,
            context
        ) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading WFS/Postgis Layer to GeoServer...")
        
        data_in_json = render_to_string('govapp/geoserver/wfs/wfs_layer.json', context)
        layer_get_url = f"{self.service_url}/rest/workspaces/{workspace}/datastores/{store_name}/featuretypes/{layer_name}"

        # Check if Layer Exists
        response = httpx.get(
            url=layer_get_url,
            auth=(self.username, self.password),
            headers=self.headers_json,
            timeout=120.0
        )
        if response.status_code == 200:
            log.info(f'Layer: [{layer_name}] exists.  Perform delete request.')
            response = httpx.delete(
                url=layer_get_url+"?recurse=true",
                auth=(self.username, self.password),
                #data=xml_data,
                headers=self.headers_json,
                timeout=120.0
            )
        else:
            log.info(f'Layer: [{layer_name}] does not exist.')

        # Create the layer
        url = f"{self.service_url}/rest/workspaces/{workspace}/datastores/{store_name}/featuretypes"

        log.info(f'Create the layer by post request...')
        log.info(f'Post url: { url }')
        log.info(f'Post data: {data_in_json}')
        response = httpx.post(
            url=url,
            auth=(self.username, self.password),
            data=data_in_json,
            headers=self.headers_json,
            timeout=300.0
        )
        log.info(f"GeoServer WFS response: '{response.status_code}: {response.text}'")
        
        # Check Response
        response.raise_for_status()

    @handle_http_exceptions(log)
    def upload_style(
        self,
        workspace: str,
        style_name: str,
        new_sld: str,
        use_raw: bool = False
    ):
        """Uploads an SLD Style to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload style for.
            name (str): Name of the style.
            sld (str): Style to upload.
        """
        try:
            if not new_sld:
                log.warning(f'SLD is None/empty.  Stop uploading the style: [{style_name}].')
                return False
            
            parameters = ''
            if use_raw:
                parameters = '?raw=true'

            # Retrieve Existing Style
            existing_sld = self.get_style(workspace, style_name)

            # Check if Style Exists
            if not existing_sld:
                # Log
                log.info(f"Creating Style Metadata file: '{style_name}.xml' in GeoServer: [{self.service_url}]...")

                # Create the Style
                url = f"{self.service_url}/rest/workspaces/{workspace}/styles{parameters}"

                # Perform Request
                response = httpx.post(
                    url=url,
                    json={
                        "style": {
                            "name": style_name,
                            "filename": f"{style_name}.sld"
                        }
                    },
                    auth=(self.username, self.password),
                    timeout=120.0
                )

                # Log
                log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

                # Check Response
                response.raise_for_status()

            # Log
            log.info(f"Creating/Updating the Style '{style_name}.sld' in the GeoServer: [{self.service_url}]...")

            # Upload the Style
            url = f"{self.service_url}/rest/workspaces/{workspace}/styles/{style_name}.xml{parameters}"

            # Perform Request
            response = httpx.put(
                url=url,
                content=new_sld,
                headers={"Content-Type": "application/vnd.ogc.sld+xml"},
                auth=(self.username, self.password),
                timeout=120.0
            )

            # Log
            log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

            # Check Response
            response.raise_for_status()

            return True
        except Exception as e:
            log.error(f"Unable to create/update the style: [{style_name}] to the GeoServer: [{self.service_url}]: {e}")

    @handle_http_exceptions(log)
    def get_style(
        self,
        workspace: str,
        name: str,
    ) -> Optional[str]:
        """Retrieves a style from the GeoServer if it exists.

        Args:
            workspace (str): Workspace to upload files to.
            name (str): Name of the style to retrieve.

        Returns:
            Optional[str]: The XML SLD if the style exists, otherwise None.
        """
        # Log
        log.info(f"Checking Style '{name}' existence in GeoServer")

        # Construct URL
        url = f"{self.service_url}/rest/workspaces/{workspace}/styles/{name}.sld"

        # Perform Request
        response = httpx.get(
            url=url,
            auth=(self.username, self.password),
            timeout=120.0
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        if response.is_success:
            # Return Text
            return response.text

        # Return None
        return None

    @handle_http_exceptions(log)
    def set_default_style_to_layer(
        self,
        style_name: str,
        workspace_name: str,
        layer_name: str,
    ) -> None:
        """
        Sets the default style for a layer in GeoServer by fetching,
        modifying, and putting back the layer configuration.
        """
        log.info(f"Setting default style '{style_name}' for layer '{layer_name}'...")

        wait_seconds = settings.WAIT_FOR_N_SECONDS_BEFORE_FETCHING_LAYER_DETAILS
        log.info(f"Waiting for {wait_seconds} seconds before fetching layer details...")
        time.sleep(wait_seconds)

        # --- Step 1: GET the current layer configuration ---
        get_url = f"{self.service_url}/rest/layers/{workspace_name}:{layer_name}.xml"
        
        try:
            log.info(f"Fetching current layer details from: {get_url}")
            get_response = httpx.get(
                url=get_url,
                auth=(self.username, self.password),
                timeout=30.0
            )
            get_response.raise_for_status()

            # --- Step 2: Parse the XML and modify the defaultStyle ---
            # Parse the XML content from the response
            tree = ET.fromstring(get_response.content)

            # Find the <defaultStyle> element. If it doesn't exist, create it.
            default_style_element = tree.find('defaultStyle')
            if default_style_element is None:
                default_style_element = ET.SubElement(tree, 'defaultStyle')

            # Find the <name> element within <defaultStyle>. If it doesn't exist, create it.
            name_element = default_style_element.find('name')
            if name_element is None:
                name_element = ET.SubElement(default_style_element, 'name')

            # Set the new style name
            name_element.text = style_name
            
            # Convert the modified XML tree back to a string
            updated_xml_content = ET.tostring(tree, encoding='unicode')

            # --- Step 3: PUT the modified full layer configuration back ---
            put_url = f"{self.service_url}/rest/layers/{workspace_name}:{layer_name}.xml" # Can also use the same URL
            log.info(f"Putting updated layer configuration to: {put_url}")
            log.debug(f"Updated XML Payload: {updated_xml_content}") # For debugging

            put_response = httpx.put(
                url=put_url,
                content=updated_xml_content,
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
                timeout=120.0
            )
            put_response.raise_for_status()
            log.info(f"Successfully set default style '{style_name}' for layer '{layer_name}'.")

        except httpx.HTTPStatusError as e:
            # Provide more context on HTTP errors
            error_text = e.response.text
            log.error(
                f"HTTP error while setting default style for '{layer_name}': "
                f"Status {e.response.status_code}, Response: {error_text}"
            )
            raise  # Re-raise the exception
        except Exception as e:
            log.error(f"Unable to set the default style: [{style_name}] to the GeoServer: [{self.service_url}]: {e}")

    @handle_http_exceptions(log)
    def validate_style(self, sld: str) -> Optional[dict[str, Any]]:
        #return None
        """Validates SLD using the GeoServer OGC API.

        Args:
            sld (str): Style to validate.

        Returns:
            Optional[dict[str, Any]]: JSON of errors if applicable, otherwise
                None.
        """
        # Log
        log.info("Validating Style in GeoServer")

        # Construct URL
        url = "{0}/ogc/styles/styles".format(self.service_url)

        # Perform Request
        response = httpx.post(
            url=url,
            auth=(self.username, self.password),
            content=sld,
            params={"validate": "only"},
            headers={"Content-Type": "application/vnd.ogc.se+xml"},
            timeout=120.0
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        if response.is_error:
            # Return JSON
            return response.json()  # type: ignore[no-any-return]

        # Return None
        return None

    @handle_http_exceptions(log)
    def get_layers(self) -> Optional[list[dict[str, str]]]:
        #return None
        """Retreiving layers from GeoServer.

        Returns:
            Optional[list[dict[str, str]]]: A list of layer information
        """
        # Log
        log.info(f'Retreiving layers from GeoServer: [{self.service_url}]')
        
        # Construct URL
        url = "{0}/rest/layers".format(self.service_url)

        # Perform Request
        response = httpx.get(
            url=url,
            auth=(self.username, self.password),
            headers=self.headers_json,
            timeout=120.0
        )
        
        # Check Response
        response.raise_for_status()
        
        json_response = response.json()
        if (json_response == None or 
            hasattr(json_response, 'layers') or 
            hasattr(json_response, 'layer')):
            log.error(f"The response of retrieving layers from a GeoServer was wrong. {json_response}")
        # Return JSON
        if json_response['layers']:
            return json_response['layers']['layer']
        else:
            # No layers
            return []

    @handle_http_exceptions(log)
    def get_layer_details(self, layer_name: str) -> Optional[dict]:
        """
        Retrieve details for a specific layer from GeoServer.

        Args:
            layer_name (str): The name of the layer to retrieve details for.

        Returns:
            Optional[dict]: The details of the layer, or None if not found.
        """
        # Log
        log.info(f'Retrieving details for layer: [{layer_name}] from GeoServer: [{self.service_url}]')
        
        # Construct URL
        url = f"{self.service_url}/rest/layers/{layer_name}"
        
        # Perform Request
        response = httpx.get(
            url=url,
            auth=(self.username, self.password),
            headers=self.headers_json,
            timeout=120.0
        )

        # Check Response
        response.raise_for_status()

        json_response = response.json()
        if json_response is None or not json_response.get('layer'):
            log.error(f"The response of retrieving details for layer [{layer_name}] from GeoServer was wrong. {json_response}")
            return None
        
        # Return JSON
        # return json_response['layer']
        return json_response

    @handle_http_exceptions(log)
    def delete_layer(self, layer_name) -> None:
        try:
            # --- PRE-DELETION: IDENTIFY STYLES TO WATCH ---
            # First, get the layer details before it's gone.
            log.info(f"Preparing to delete layer: [{layer_name}]. Fetching details first...")
            layer_details_response = self.get_layer_details(layer_name)

            if not layer_details_response or 'layer' not in layer_details_response:
                log.warning(f"Could not retrieve details for layer [{layer_name}]. It might already be deleted. Skipping style cleanup.")
                # If the layer doesn't exist, there's nothing to do.
                return
            
            layer_data = layer_details_response['layer']
            styles_to_check = set()

            # Check for the default style and add it to my set.
            if 'defaultStyle' in layer_data and 'name' in layer_data['defaultStyle']:
                styles_to_check.add(layer_data['defaultStyle']['name'])
            
            # Also check for any other associated styles.
            if 'styles' in layer_data and 'style' in layer_data.get('styles', {}):
                for style in layer_data['styles']['style']:
                    styles_to_check.add(style['name'])

            log.info(f"Layer [{layer_name}] uses the following styles: {list(styles_to_check)}. check them for cleanup after deletion.")
            # --- END PRE-DELETION ---

            # --- EXECUTION: DELETE LAYER AND STORE ---
            # Delete Layer
            log.info(f"Deleting layer resource: [{layer_name}]...")
            layer_delete_url = f"{self.service_url}/rest/layers/{layer_name}"
            response = httpx.delete(
                        url=layer_delete_url,
                        auth=(self.username, self.password),
                        headers=self.headers_json,
                        timeout=120.0
                    )
            response.raise_for_status()
            if response.status_code == 200:
                log.info(f'Layer: [{layer_name}] deleted successfully from the geoserver: [{self.service_url}].')
            else:
                log.error(f'Failed to delete layer: [{layer_name}].  {response.status_code} {response.text}')

            # Delete store
            workspace_and_layer = layer_details_response['layer']['resource']['name'].split(':')
            if layer_details_response['layer']['type'] == 'VECTOR':
                store_delete_url = f"{self.service_url}/rest/workspaces/{ workspace_and_layer[0] }/datastores/{ workspace_and_layer[1] }"
            else:
                store_delete_url = f"{self.service_url}/rest/workspaces/{ workspace_and_layer[0] }/coveragestores/{ workspace_and_layer[1] }"
            response = httpx.delete(
                        url=store_delete_url + '?recurse=true',
                        auth=(self.username, self.password),
                        headers=self.headers_json,
                        timeout=120.0
                    )
            response.raise_for_status()
            log.info(f"Store [{workspace_and_layer[1]}] deleted successfully.")
            # --- END: EXECUTION: DELETE LAYER AND STORE ---

            # --- POST-DELETION: CLEANUP STYLES ---
            if not styles_to_check:
                log.info("No styles were associated with the deleted layer. Cleanup is not needed.")
                return

            log.info("Checking for orphaned styles...")
            # get a fresh list of all styles that are still in use.
            all_currently_used_styles = self.get_used_styles()

            # must not delete the built-in styles by accident.
            protected_styles = set(settings.GEOSERVER_PROTECTED_STYLES)

            for style_name in styles_to_check:
                # If a style I was watching is NOT in the new list of used styles, it's an orphan.
                if style_name not in all_currently_used_styles:
                    if style_name in protected_styles:
                        log.warning(f"Style [{style_name}] is a protected style. Skipping deletion.")
                        continue
                    
                    log.info(f"Style [{style_name}] is now orphaned. Proceeding with deletion.")
                    # Delete style
                    self.delete_style(style_name)
                else:
                    # If it's still in the list, another layer is using it.
                    log.info(f"Style [{style_name}] is still in use by another layer. It will be kept.")
            # --- END: POST-DELETION: CLEANUP STYLES ---

        except Exception as e:
            log.error(f'Failed to delete layer: [{layer_name}].  {str(e)}')
            raise

    @handle_http_exceptions(log)
    def get_used_styles(self) -> set[str]:
        """
        Get a set of all style names currently used by any layer.
        """
        log.info("Checking all layers to determine which styles are in use...")
        used_styles = set()
        
        # First, get a list of all layers.
        layers = self.get_layers()
        if not layers:
            log.info("No layers found in GeoServer.")
            return used_styles
        
        # Iterate through each layer to get its details.
        for layer_item in layers:
            layer_name = layer_item['name']
            
            details_data = self.get_layer_details(layer_name)
            
            if details_data and 'layer' in details_data:
                layer = details_data['layer']
                
                # Add the layer's default style.
                if 'defaultStyle' in layer and 'name' in layer['defaultStyle']:
                    used_styles.add(layer['defaultStyle']['name'])
                
                # Also add any alternate styles associated with the layer.
                if 'styles' in layer and 'style' in layer.get('styles', {}):
                    for style in layer['styles']['style']:
                        used_styles.add(style['name'])

        log.info(f"Found {len(used_styles)} styles currently in use.")
        return used_styles

    @handle_http_exceptions(log)
    def delete_style(self, style_name: str, purge: bool = True) -> None:
        """
        Delete a single style by its name from GeoServer.
        """
        # I'm making sure to include `purge=true` to remove the SLD file itself.
        log.info(f"Deleting style: [{style_name}] from the GeoServer: [{self.service_url}]...")
        url = f"{self.service_url}/rest/styles/{style_name}?purge={str(purge).lower()}"
        
        response = httpx.delete(
            url=url,
            auth=self.auth,
            timeout=120.0
        )
        response.raise_for_status()
        log.info(f"Successfully deleted style: [{style_name}] from the geoserver: [{self.service_url}].")

def geoserver() -> GeoServer:
    """Helper constructor to instantiate GeoServer.

    Returns:
        GeoServer: Configured GeoServer instance.
    """
    # Construct and Return
    return GeoServer(
        service_url=conf.settings.GEOSERVER_URL,
        username=conf.settings.GEOSERVER_USERNAME,
        password=conf.settings.GEOSERVER_PASSWORD,
    )


def geoserverWithCustomCreds(url,username,password):
    return GeoServer(
        service_url=url,
        username=username,
        password=password,
    )
