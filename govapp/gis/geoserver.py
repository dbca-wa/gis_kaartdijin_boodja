"""GeoServer Abstractions."""


# Standard
import asyncio
import json
import logging
import pathlib

# Third-Party
from django import conf
import httpx

# Typing
from typing import Any, Optional
from django.template.loader import render_to_string

from govapp import settings
from govapp.common.utils import calculate_dict_differences, handle_http_exceptions

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

    @handle_http_exceptions(log)
    def create_workspace_if_not_exists(self, workspace_name):
        # URL to check the existence of the workspace
        workspace_url = f"{self.service_url}/rest/workspaces/{workspace_name}.json"

        # Headers with authentication information
        headers = {'Content-Type': 'application/json'}

        with httpx.Client(auth=(self.username, self.password)) as client:
            # Send a GET request to check the existence of the workspace
            response = client.get(workspace_url, headers=headers)

        # Create the workspace only if it doesn't exist
        if response.status_code == 404:
            log.info(f"Workspace '{workspace_name}' does not exist in the geoserver: [{self.service_url}]. Creating...")

            # URL to create the workspace
            create_workspace_url = f"{self.service_url}/rest/workspaces"

            # JSON data required to create the workspace
            workspace_data = {
                "workspace": {
                    "name": workspace_name
                }
            }

            with httpx.Client(auth=(self.username, self.password)) as client:
                # Send a POST request to create the workspace
                create_response = client.post(create_workspace_url, headers=headers, json=workspace_data)

            # Check the status code to determine if the creation was successful
            if create_response.status_code == 201:
                log.info(f"Workspace '{workspace_name}' created successfully in the geoserver: [{self.service_url}].")
            else:
                log.info("Failed to create workspace.")
                log.info(create_response.text)
        else:
            log.info(f"Workspace '{workspace_name}' already exists in the geoserver: [{self.service_url}].")

    @handle_http_exceptions(log)
    def create_store_if_not_exists(self, workspace_name, store_name, data):
        # URL to check the existence of the store
        store_get_url = f"{self.service_url}/rest/workspaces/{workspace_name}/wmsstores/{store_name}"
        log.info(f'store_get_url: {store_get_url}')

        # Headers with authentication information
        headers = {'Content-Type': 'application/json'}

        # Check if Store Exists
        log.info(f'Checking if the store exists...')
        with httpx.Client(auth=(self.username, self.password)) as client:
            response = client.get(store_get_url, headers=headers)

        # Construct URL
        url = f"{self.service_url}/rest/workspaces/{workspace_name}/wmsstores"

        # Decide whether to perform a POST or PUT request based on the existence of the store
        if response.status_code == 404: 
            # Store does not exist, perform a POST request
            log.info(f'Store does not exist. Performing POST request.')
            log.info(f'POST url: {url}')
            log.debug(f'data: {data}')
            with httpx.Client(auth=(self.username, self.password)) as client:
                response = client.post(url=url, headers=headers, json=data)

        else:          
            # Store exists, perform a PUT request
            log.info(f'Store exists. Performing PUT request.')
            log.info(f'PUT url: {store_get_url}')
            log.debug(f'data: {data}')
            with httpx.Client(auth=(self.username, self.password)) as client:
                response = client.put(url=store_get_url, headers=headers, json=data)
            
        return response

    @handle_http_exceptions(log)
    def upload_geopackage(
        self,
        workspace: str,
        layer: str,
        filepath: pathlib.Path,
    ) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload GeoPackage for.
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading Geopackage '{filepath}' to GeoServer")

        # Construct URL
        url = "{0}/rest/workspaces/{1}/datastores/{2}/file.gpkg".format(
            self.service_url,
            workspace,
            layer,
        )

        # Perform Request
        response = httpx.put(
            url=url,
            content=filepath.read_bytes(),
            params={"filename": filepath.name, "update": "overwrite"},
            auth=(self.username, self.password),
            timeout=120.0
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        response.raise_for_status()

    @handle_http_exceptions(log)
    def upload_tif(
        self,
        workspace: str,
        layer: str,
        filepath: pathlib.Path,
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

        # Perform Request
        response = httpx.put(
            url=url,
            content=filepath.read_bytes(),
            params={
                "filename": filepath.name,
                "update": "overwrite",
                "configure": "all"
                },
            auth=(self.username, self.password),
            timeout=3000.0
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        response.raise_for_status()

    @handle_http_exceptions(log)
    def create_layer_from_coveragestore(self, workspace: str, layer: str) -> None:
        """
        Creates a layer in GeoServer from an existing coverage store.

        Args:
            workspace (str): Workspace where the coverage store exists.
            layer (str): Name of the layer to create in GeoServer.
        """
        response_data = self.get_layer_details(layer)
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
        # layers_url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{layer}_store/coverages"
        # layers_url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{layer}/reset"
        layers_url = f"{self.service_url}/rest/layers/{workspace}:{layer}.json"

        # response_data['layer']['defaultStyle'] = {"name": "raster"}
        # response_data['layer']['resource']['srs'] = "EPSG:4326"
        # response_data['layer']['resource']['boundingBox'] = {
        #     "nativeBoundingBox": {
        #         "minx": -180,
        #         "miny": -90,
        #         "maxx": 180,
        #         "maxy": 90,
        #         "crs": "EPSG:4326"
        #     },
        #     "latLonBoundingBox": {
        #         "minx": -180,
        #         "miny": -90,
        #         "maxx": 180,
        #         "maxy": 90,
        #         "crs": "EPSG:4326"
        #     }
        # }
        
        # Perform POST request to create the layer
        response = httpx.put(
            url=layers_url,
            content=json.dumps(response_data),
            # content=json.dumps({
            #     "coverage": {
            #         # "name": f'{workspace}:{layer}',
            #         # "name": f'{workspace}',
            #         # "name": f'{layer}',
            #         # "name": "aho1", #201, 500
            #         # "name": "aho2", #201, 500
            #         "title": f'{layer}',
            #         "enabled": True
            #     }
            # }),
            headers={"Content-type": "application/json"},
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

        response = self.create_store_if_not_exists(workspace, store_name, data)
        
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
            log.info(f'xml_data: { xml_data }')

            layer_get_url = "{0}/rest/workspaces/{1}/wmsstores/{2}/wmslayers/{3}".format(
                self.service_url,
                workspace,
                store_name,
                layer_name
            )
            log.info(f'layer_get_url: {layer_get_url}')

            # Check if Layer Exists
            log.info(f'Checking if the layer exists...')
            response = httpx.get(
                url=layer_get_url+"",
                auth=(self.username, self.password),
                headers={"content-type": "application/json","Accept": "application/json"},
                timeout=120.0
            )

            log.info(f'Response of the check: { response.status_code }: { response.text }')

            if response.status_code == 200:
                log.info("Layer exists.  Delete it...")
                response = httpx.delete(
                    url=layer_get_url+"?recurse=true",
                    auth=(self.username, self.password),
                    #data=xml_data,
                    headers={"content-type": "application/json","Accept": "application/json"},
                    timeout=120.0
                )
            else:
                log.info(f'Layer does not exist.')

            # Construct URL
            url = "{0}/rest/workspaces/{1}/wmsstores/{2}/wmslayers/".format(
                self.service_url,
                workspace,
                store_name
            )

            log.info(f'Creat the layer by post request...')
            log.info(f'Post url: { url }')
            log.info(f'data: {xml_data}')
            response = httpx.post(
                url=url,
                auth=(self.username, self.password),
                data=xml_data,
                headers={"content-type": "application/json","Accept": "application/json"},
                timeout=3000
            )

            # if response.status_code == 404: 
            #     # Perform Request
            #     response = httpx.post(
            #         url=url,
            #         auth=(self.username, self.password),
            #         data=xml_data,
            #         headers={"content-type": "application/json","Accept": "application/json"}
            #     )
            #     print ("404")
            #     print (response.text)
            # else:          
            #     # Perform Request
            #     response = httpx.put(
            #         url=store_get_url,
            #         auth=(self.username, self.password),
            #         data=xml_data,
            #         headers={"content-type": "application/json","Accept": "application/json"}
            #     )

            # log.info(response.text)
            
            # Log
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
        
        xml_data = render_to_string('govapp/geoserver/wfs/wfs_layer.json', context)

        layer_get_url = "{0}/rest/workspaces/{1}/datastores/{2}/featuretypes/{3}".format(
            self.service_url,
            workspace,
            store_name,
            layer_name
        )

        # Check if Layer Exists
        response = httpx.get(
            url=layer_get_url,
            auth=(self.username, self.password),
            headers={"content-type": "application/json","Accept": "application/json"},
            timeout=120.0
        )
        if response.status_code == 200:
            log.info(f'Layer exists.  Perform delete request.')
            response = httpx.delete(
                url=layer_get_url+"?recurse=true",
                auth=(self.username, self.password),
                #data=xml_data,
                headers={"content-type": "application/json","Accept": "application/json"},
                timeout=120.0
            )
        else:
            log.info(f'Layer does not exist.')


        # Create the layer
        url = "{0}/rest/workspaces/{1}/datastores/{2}/featuretypes".format(
            self.service_url,
            workspace,
            store_name
        )
        log.info(f'Creat the layer by post request...')
        log.info(f'Post url: { url }')
        log.info(f'Post data: {xml_data}')
        response = httpx.post(
            url=url,
            auth=(self.username, self.password),
            data=xml_data,
            # data=request_body,
            headers={"content-type": "application/json","Accept": "application/json"},
            timeout=300.0
        )
        
        # Log
        log.info(f"GeoServer WFS response: '{response.status_code}: {response.text}'")
        
        # Check Response
        response.raise_for_status()        

    @handle_http_exceptions(log)
    def upload_style(
        self,
        workspace: str,
        layer: str,
        name: str,
        sld: str,
    ) -> None:
        """Uploads an SLD Style to the GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to upload style for.
            name (str): Name of the style.
            sld (str): Style to upload.
        """
        # Retrieve Existing Style
        existing_sld = self.get_style(workspace, name)

        # Check if Style Exists
        if existing_sld is None:
            # Log
            log.info(f"Creating Style '{name}' in GeoServer")

            # Create the Style
            url = "{0}/rest/workspaces/{1}/styles".format(
                self.service_url,
                workspace,
            )

            # Perform Request
            response = httpx.post(
                url=url,
                json={
                    "style": {
                        "name": name,
                        "filename": f"{name}.sld"
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
        log.info(f"Uploading Style '{name}' to GeoServer")

        # Upload the Style
        url = "{0}/rest/workspaces/{1}/styles/{2}.xml".format(
            self.service_url,
            workspace,
            name,
        )

        # Perform Request
        response = httpx.put(
            url=url,
            content=sld,
            headers={"Content-Type": "application/vnd.ogc.se+xml"},
            auth=(self.username, self.password),
            timeout=120.0
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        response.raise_for_status()

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
        url = "{0}/rest/workspaces/{1}/styles/{2}.sld".format(
            self.service_url,
            workspace,
            name,
        )

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
    def set_default_style(
        self,
        workspace: str,
        layer: str,
        name: str,
    ) -> None:
        """Sets the default style for a layer in GeoServer.

        Args:
            workspace (str): Workspace to upload files to.
            layer (str): Name of the layer to set default style for.
            name (str): Name of the style.
        """
        # Log
        log.info(f"Setting style '{name}' as default for '{layer}' in GeoServer")

        # Set Default Layer Style
        url = "{0}/rest/workspaces/{1}/layers/{2}.xml".format(
            self.service_url,
            workspace,
            layer,
        )

        # Perform Request
        # This only works with XML (GeoServer is broken)
        response = httpx.put(
            url=url,
            content=f"<layer><defaultStyle><name>{name}</name></defaultStyle></layer>",
            headers={"Content-Type": "application/xml"},
            auth=(self.username, self.password),
            timeout=120.0
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        response.raise_for_status()

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
            headers={"content-type": "application/json","Accept": "application/json"},
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
            headers={"Content-Type": "application/json", "Accept": "application/json"},
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
        # Construct URL
        url = "{0}/rest/layers/{1}".format(self.service_url, layer_name)
        
        response = httpx.delete(
                    url=url,
                    auth=(self.username, self.password),
                    headers={"content-type": "application/json","Accept": "application/json"},
                    timeout=120.0
                )
        
        # Check Response
        response.raise_for_status()
        if response.status_code == 200:
            log.info(f'Layer: [{layer_name}] deleted successfully from the geoserver: [{self.service_url}].')
        else:
            log.error(f'Failed to delete layer: [{layer_name}].  {response.status_code} {response.text}')

    # Function to create a new group in GeoServer
    @handle_http_exceptions(log)
    def create_geoserver_group(self, group_name):
        url = f"{self.service_url}/rest/security/usergroup/group/{group_name}"
        response = httpx.post(url, auth=(self.username, self.password))
        response.raise_for_status()
        log.info(f"Created group: {group_name} on the geoserver: [{self.service_url}]")

    # Function to create a new role in GeoServer
    @handle_http_exceptions(log)
    def create_geoserver_role(self, role_name):
        url = f"{self.service_url}/rest/security/roles/role/{role_name}"
        response = httpx.post(url, auth=(self.username, self.password))
        response.raise_for_status()
        log.info(f"Created role: {role_name} on the geoserver: [{self.service_url}]")

    @handle_http_exceptions(log)
    def update_workspace_security(self, workspace_name, role_to_modify, read_permission, write_permission, admin_permission):
        """
        Update security settings for a specific workspace in GeoServer.

        :param workspace_name: The name of the workspace to update.
        :param role_to_modify: The role to modify.
        :param read_permission: Boolean value for read permission.
        :param write_permission: Boolean value for write permission.
        :param admin_permission: Boolean value for admin permission.
        """

        self.fetch_all_rules()

        security_url = f"{self.service_url}/rest/security/acl/workspaces/{workspace_name}.json"
        
        # Construct the security settings JSON payload
        security_settings = {
            "rules": [
                {
                    "role": role_to_modify,
                    "workspace": workspace_name,
                    "access": {
                        "read": read_permission,
                        "write": write_permission,
                        "admin": admin_permission
                    }
                }
            ]
        }
        
        with httpx.AsyncClient() as client:
            response = client.put(
                security_url,
                json=security_settings,
                auth=(self.username, self.password),
                headers={'Content-Type': 'application/json'}
            )
        
        if response.status_code == 200:
            log.info(f"Security settings updated successfully for workspace '{workspace_name}' and role '{role_to_modify}'.")
        else:
            log.error(f"Failed to update security settings: {response.status_code}, Response: {response.text}")

    def synchronize_rules(self, new_rules):
        from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerRolePermission

        existing_rules = self.fetch_rules()

        items_to_update, items_to_create, items_to_delete = calculate_dict_differences(new_rules, existing_rules)

        log.info(f'Rules to update: {json.dumps(items_to_update, indent=4)}')
        log.info(f'Rules to create: {json.dumps(items_to_create, indent=4)}')
        log.info(f'Rules to delete: {json.dumps(items_to_delete, indent=4)}')

        # Create new rules
        if items_to_create:
            self.create_rules(items_to_create)

        # Update existing rules
        if items_to_update:
            self.update_rules(items_to_update)

        # Delete existing rules
        if items_to_delete:
            for key in items_to_delete.keys():
                self.delete_rule(key)

    @handle_http_exceptions(log)
    def fetch_rules(self):
        """Fetch all access control rules."""
        url = f"{self.service_url}/rest/security/acl/layers.json"
        response = httpx.get(url, auth=(self.username, self.password))
        response.raise_for_status()
        rules_data = response.json()
        log.info(f'Successfully fetched ACL rules: [{json.dumps(rules_data, indent=4)}] from the geoserver: [{self.service_url}].')
        return rules_data

    @handle_http_exceptions(log)
    def create_rules(self, rules):
        """Add a set of access control rules."""
        url = f"{self.service_url}/rest/security/acl/layers"
        headers = {'Content-Type': 'application/json'}
        response = httpx.post(url, json=rules, headers=headers, auth=(self.username, self.password))
        response.raise_for_status()
        log.info(f'Successfully added ACL rules: [{json.dumps(rules)}].')
        return {}

    @handle_http_exceptions(log)
    def update_rules(self, rules):
        """Modify a set of access control rules."""
        url = f"{self.service_url}/rest/security/acl/layers"
        headers = {'Content-Type': 'application/json'}
        response = httpx.put(url, json=rules, headers=headers, auth=(self.username, self.password))
        response.raise_for_status()
        log.info(f'Successfully updated ACL rules: [{json.dumps(rules)}].')
        return {}

    @handle_http_exceptions(log)
    def delete_rule(self, key):
        """Delete a specific access control rule."""
        url = f"{self.service_url}/rest/security/acl/layers/{key}"
        response = httpx.delete(url, auth=(self.username, self.password))
        response.raise_for_status()
        log.info(f'Successfully deleted ACL rule: key=[{key}].')
        return {}

# Example usage:
# geoserver_acl = GeoServerACL('http://example.com/geoserver', 'admin', 'password')
# rules = geoserver_acl.fetch_rules()
# geoserver_acl.add_rules({"newworkspace.newlayer.r": "ROLE_3,ROLE_4"})
# geoserver_acl.update_rules({"newworkspace.newlayer.r": "ROLE_5,ROLE_6"})
# geoserver_acl.delete_rule("newworkspace.newlayer.r")

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



