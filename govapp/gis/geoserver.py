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
        if memory_map_size is not None:
            # The key for the query parameter is 'mmap'.
            params['mmap'] = str(memory_map_size)

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
                    if not status_url:
                        log.warning("GeoServer returned 202 but no Location header. Waiting a fixed time.")
                        time.sleep(5) # Fallback delay
                        return

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
                # --- END: NEW ASYNCHRONOUS TASK HANDLING ---

            except requests.exceptions.RequestException as e:
                log.error(f'Upload failed: [{str(e)}]')
                raise

    @handle_http_exceptions(log)
    def upload_tif(
        self,
        workspace: str,
        layer: str,
        filepath: pathlib.Path,
        chunk_size: Optional[int] = 1024 * 1024  # 1MB chunks by default
    ) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading GeoTiff '{filepath}' to GeoServer")

        # Construct URL
        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{layer}/file.geotiff"
        
        headers = {
            'Content-Type': 'image/tiff',
            'Transfer-Encoding': 'chunked',
            'Connection': 'keep-alive'
        }
        
        params = {
            'filename': layer,
            'update': 'overwrite',
            'configure': 'all',
            # 'coverageName': layer
        }

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
                    timeout=3000.0,
                    stream=True
                )

                log.info(f"GeoServer response: '{response.status_code}: {response.text}'")
                response.raise_for_status()

            except requests.exceptions.RequestException as e:
                log.error(f'Upload failed: [{str(e)}]')
                raise

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

        wait_seconds = 5
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
