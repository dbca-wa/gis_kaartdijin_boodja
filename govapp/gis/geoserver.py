"""GeoServer Abstractions."""


# Standard
import logging
import pathlib

# Third-Party
from django import conf
import httpx

# Typing
from typing import Optional


# Logging
log = logging.getLogger(__name__)


class GeoServer:
    """GeoServer Abstraction."""

    def __init__(
        self,
        service_url: str = conf.settings.GEOSERVER_URL,
        username: str = conf.settings.GEOSERVER_USERNAME,
        password: str = conf.settings.GEOSERVER_PASSWORD,
        workspace: str = conf.settings.GEOSERVER_WORKSPACE,
    ) -> None:
        """Instantiates the GeoServer Abstraction.

        Args:
            service_url (str): URL to the GeoServer service.
            username (str): Username for the GeoServer service.
            password (str): Password for the GeoServer service.
            workspace (str): Workspace to upload files to.
        """
        # Instance Attributes
        self.service_url = service_url.rstrip("/")  # Strip trailing slash
        self.username = username
        self.password = password
        self.workspace = workspace

    def upload_geopackage(self, filepath: pathlib.Path) -> None:
        """Uploads a Geopackage file to the GeoServer.

        Args:
            filepath (pathlib.Path): Path to the Geopackage file to upload.
        """
        # Log
        log.info(f"Uploading Geopackage '{filepath}' to GeoServer")

        # Construct URL
        url = "{0}/rest/workspaces/{1}/datastores/{2}/file.gpkg?filename={3}".format(
            self.service_url,
            self.workspace,
            filepath.stem,
            filepath.name,
        )

        # Perform Request
        response = httpx.put(
            url=url,
            content=filepath.read_bytes(),
            params={"update": "overwrite"},
            auth=(self.username, self.password),
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        response.raise_for_status()

    def upload_style(self, name: str, sld: str) -> None:
        """Uploads an SLD Style to the GeoServer.

        Args:
            name (str): Name of the style.
            sld (str): Style to upload.
        """
        # Retrieve Existing Style
        existing_sld = self.get_style(name)

        # Check if Style Exists
        if existing_sld is None:
            # Log
            log.info(f"Creating Style '{name}' in GeoServer")

            # Create the Style
            url = "{0}/rest/workspaces/{1}/styles".format(
                self.service_url,
                self.workspace,
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
            )

            # Log
            log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

            # Check Response
            response.raise_for_status()

            # Log
            log.info(f"Setting Style '{name}' as Default in GeoServer")

            # Set Default Layer Style
            # Note: Assumes that style name and layer name are the same
            url = "{0}/rest/workspaces/{1}/layers/{2}.xml".format(
                self.service_url,
                self.workspace,
                name,
            )

            # Perform Request
            # This only works with XML (GeoServer is broken)
            response = httpx.put(
                url=url,
                content=f"<layer><defaultStyle><name>{name}</name></defaultStyle></layer>",
                headers={"Content-Type": "application/xml"},
                auth=(self.username, self.password),
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
            self.workspace,
            name,
        )

        # Perform Request
        response = httpx.put(
            url=url,
            content=sld,
            headers={"Content-Type": "application/vnd.ogc.se+xml"},
            auth=(self.username, self.password),
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        response.raise_for_status()

    def get_style(self, name: str) -> Optional[str]:
        """Retrieves a style from the GeoServer if it exists.

        Args:
            name (str): Name of the style to retrieve.

        Returns:
            Optional[str]: The XML SLD if the style exists, otherwise None.
        """
        # Log
        log.info(f"Checking Style '{name}' existence in GeoServer")

        # Construct URL
        url = "{0}/rest/workspaces/{1}/styles/{2}.sld".format(
            self.service_url,
            self.workspace,
            name,
        )

        # Perform Request
        response = httpx.get(
            url=url,
            auth=(self.username, self.password),
        )

        # Log
        log.info(f"GeoServer response: '{response.status_code}: {response.text}'")

        # Check Response
        if response.is_success:
            # Return Text
            return response.text

        # Return None
        return None
