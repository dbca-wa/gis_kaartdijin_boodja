"""Kaartdijin Boodja Publisher Django Application Publish Channel Models."""


# Standard
import logging
import pathlib
import shutil
import os
import ftplib

# Third-Party
from django import conf
from django.db import models
from django.core import exceptions
from django.utils import timezone
import httpx
import reversion
from django.template import Template, Context
from django.core.validators import MinValueValidator
from datetime import datetime

# Local
from govapp import gis
from govapp.apps.publisher.models.geoserver_pools import GeoServerPool
from govapp.common import azure
from govapp.common import mixins
from govapp.common import sharepoint
from govapp.apps.publisher.models import publish_entries
from govapp.apps.publisher.models import workspaces
from govapp.gis.geoserver import geoserverWithCustomCreds


# Logging
log = logging.getLogger(__name__)


class PublishChannelFrequency(models.IntegerChoices):
    """Enumeration for a Publish Channel Frequency."""
    ON_CHANGE = 1


class CDDPPublishChannelMode(models.IntegerChoices):
    """Enumeration for a CDDP Publish Channel Mode."""
    AZURE = 1
    AZURE_AND_SHAREPOINT = 2


class CDDPPublishChannelFormat(models.IntegerChoices):
    """Enumeration for a Publish Channel Format."""
    GEOPACKAGE = 1
    SHAPEFILE = 2
    GEODATABASE = 3
    GEOJSON = 4

class FTPPublishChannelFormat(models.IntegerChoices):
    """Enumeration for a Publish Channel Format."""
    GEOPACKAGE = 1
    SHAPEFILE = 2
    GEODATABASE = 3
    GEOJSON = 4


@reversion.register()
class CDDPPublishChannel(mixins.RevisionedMixin):
    """Model for a CDDP Publish Channel."""
    
    name = models.TextField(blank=True, null=True, default='')
    #description = models.TextField(blank=True)    
    published_at = models.DateTimeField(blank=True, null=True)
    format = models.IntegerField(choices=CDDPPublishChannelFormat.choices)  # noqa: A003
    mode = models.IntegerField(choices=CDDPPublishChannelMode.choices)
    frequency = models.IntegerField(choices=PublishChannelFrequency.choices)
    path = models.TextField()
    xml_path = models.TextField(blank=True, null=True)
    publish_entry = models.ForeignKey(
        # publish_entries.PublishEntry,
        'PublishEntry',
        related_name="cddp_channels",
        on_delete=models.CASCADE,
    )

    class Meta:
        """CDDP Publish Channel Model Metadata."""
        verbose_name = "CDDP Publish Channel"
        verbose_name_plural = "CDDP Publish Channels"

    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.name}"

    def publish(self, symbology_only: bool = False) -> None:
        """Publishes the Catalogue Entry to this channel if applicable.

        Args:
            symbology_only (bool): Whether to publish symbology only.
        """
        # Log
        log.info(f"Attempting to publish '{self.publish_entry}' to channel '{self}'")

        # Check Symbology Only Flag
        if symbology_only:
            # Log
            log.info(f"Skipping due to {symbology_only=}")

            # Exit Early
            return

        # Check Mode
        match self.mode:
            case CDDPPublishChannelMode.AZURE:
                # Publish only to Azure
                self.publish_azure()

            case CDDPPublishChannelMode.AZURE_AND_SHAREPOINT:
                # Publish to Azure and Sharepoint
                self.publish_azure()
                self.publish_sharepoint()

        # Update Published At
        publish_time = timezone.now()
        self.publish_entry.published_at = publish_time
        self.publish_entry.save()
        self.published_at = publish_time
        self.save()

    def publish_azure(self) -> None:
        """Publishes the Catalogue Entry to Azure if applicable."""
        log.info(f"Publishing CDDPPublishChannel obj: [{self}] to Azure...")
       
        filepath = pathlib.Path(self.publish_entry.catalogue_entry.active_layer.file)
        log.info(f'active_layer filepath: [{filepath}]')

        # Select Conversion Function
        match self.format:
            case CDDPPublishChannelFormat.GEOPACKAGE:
                function = gis.conversions.to_geopackage
            case CDDPPublishChannelFormat.SHAPEFILE:
                function = gis.conversions.to_shapefile
            case CDDPPublishChannelFormat.GEODATABASE:
                function = gis.conversions.to_geodatabase
            case CDDPPublishChannelFormat.GEOJSON:
                function = gis.conversions.to_geojson

        publish_directory = function(
            filepath=filepath,
            layer=self.publish_entry.name,
            catalogue_name=self.publish_entry.catalogue_entry.name,
            export_method='cddp'
        )

        # # Construct Path
        output_path = pathlib.Path(conf.settings.AZURE_OUTPUT_SYNC_DIRECTORY + os.path.sep + self.path)
        if not os.path.exists(output_path):
            os.makedirs(output_path)

        geodb_dir = ""
        if self.format == CDDPPublishChannelFormat.GEODATABASE:
            file_names_geodb = os.listdir(publish_directory['uncompressed_filepath'])
            if len(file_names_geodb) == 1:
                geodb_dir = file_names_geodb[0]

        file_names = os.listdir(pathlib.Path(str(publish_directory['uncompressed_filepath']) + os.path.sep + str(geodb_dir)))
        for file_name in file_names:            
            new_output_path = os.path.join(output_path,file_name)
            if self.format == CDDPPublishChannelFormat.GEODATABASE:
                if len(new_output_path) > 0:
                    if os.path.isdir(new_output_path):
                        shutil.rmtree(pathlib.Path(new_output_path))
                    if os.path.isfile(new_output_path):
                        os.remove(new_output_path)   

            else:
                if os.path.isfile(new_output_path):
                    os.remove(new_output_path)
            source_path = os.path.join(pathlib.Path(str(publish_directory['uncompressed_filepath']) + os.path.sep + str(geodb_dir)), file_name)
            destination_path = os.path.join(output_path, file_name)
            shutil.copyfile(source_path, destination_path)
            os.unlink(source_path)

        if self.format == CDDPPublishChannelFormat.GEODATABASE:
            # Copy XML from orignal spatial archive.
            xml_file = pathlib.Path(str(publish_directory['filepath_before_flatten']) + os.path.sep + self.name + ".xml")
            if os.path.isfile(xml_file):
                xml_output_path = pathlib.Path(conf.settings.AZURE_OUTPUT_SYNC_DIRECTORY)
                if self.xml_path:
                    xml_output_path = xml_output_path.joinpath(self.xml_path)
                log.info(f'Copy xml_file: [{xml_file}] to xml_output_path: [{xml_output_path}].')
                shutil.copy(xml_file, xml_output_path)

    def publish_sharepoint(self) -> None:
        """Publishes the Catalogue Entry to SharePoint if applicable."""
        # Log
        log.info(f"Publishing '{self}' to SharePoint")

        # Retrieve the Layer File from Storage
        filepath = pathlib.Path(self.publish_entry.catalogue_entry.active_layer.file)  

        # Select Conversion Function
        match self.format:
            case CDDPPublishChannelFormat.GEOPACKAGE:
                function = gis.conversions.to_geopackage
            case CDDPPublishChannelFormat.SHAPEFILE:
                function = gis.conversions.to_shapefile
            case CDDPPublishChannelFormat.GEODATABASE:
                function = gis.conversions.to_geodatabase
            case CDDPPublishChannelFormat.GEOJSON:
                function = gis.conversions.to_geojson

        # Convert Layer to Chosen Format
        publish_directory = function(
            filepath=filepath,
            layer=self.publish_entry.catalogue_entry.metadata.name,
            catalogue_name=self.publish_entry.catalogue_entry.name,
            export_method='cddp'
        )    

        geodb_dir = ""
        if self.format == CDDPPublishChannelFormat.GEODATABASE:
            file_names_geodb = os.listdir(publish_directory['uncompressed_filepath'])
            if len(file_names_geodb) == 1:
                geodb_dir = file_names_geodb[0]

        # Push to Sharepoint
        file_names = os.listdir(os.path.join(publish_directory['uncompressed_filepath'],geodb_dir))        
        for file_name in file_names:            
            new_output_path = os.path.join(conf.settings.SHAREPOINT_OUTPUT_PUBLISH_AREA,self.path,file_name)            
            sharepoint.sharepoint_output().put(
                path=new_output_path,
                contents=pathlib.Path(os.path.join(publish_directory['uncompressed_filepath'],geodb_dir,file_name)).read_bytes(),
            )

        if self.format == CDDPPublishChannelFormat.GEODATABASE:
            # Copy XML from orignal spatial archive.
            if len(self.xml_path) > 1:
                xml_file = pathlib.Path(str(publish_directory['filepath_before_flatten']) + os.path.sep + self.name + ".xml")
                print (xml_file)
                if os.path.isfile(xml_file):
                    new_output_path = os.path.join(conf.settings.SHAREPOINT_OUTPUT_PUBLISH_AREA,self.xml_path,self.name + ".xml")            
                    sharepoint.sharepoint_output().put(
                        path=new_output_path,
                        contents=pathlib.Path(os.path.join(xml_file)).read_bytes(),
                    )


class GeoServerPublishChannelMode(models.IntegerChoices):
    """Enumeration for a GeoServer Publish Channel Mode."""
    WMS = 1
    WMS_AND_WFS = 2


class StoreType(models.IntegerChoices):
    GEOPACKAGE = 1, 'GeoPackage'
    GEOTIFF = 2, 'GeoTiff'


class GeoServerPublishChannelManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('workspace', 'publish_entry', 'geoserver_pool')


@reversion.register()
class GeoServerPublishChannel(mixins.RevisionedMixin):
    """Model for a GeoServer Publish Channel."""
    #name = models.TextField()
    #description = models.TextField(blank=True)
    description = models.TextField(blank=True)
    published_at = models.DateTimeField(blank=True, null=True)
    mode = models.IntegerField(choices=GeoServerPublishChannelMode.choices)
    frequency = models.IntegerField(choices=PublishChannelFrequency.choices)
    workspace = models.ForeignKey(
        workspaces.Workspace,
        related_name="publish_channels",
        on_delete=models.PROTECT,
    )
    # publish_entry = models.OneToOneField(
    publish_entry = models.ForeignKey(  # We want 1toM relation between publish_entry and geoserver_pool.  That's why changing this relation from 1to1 to 1toM.
        # publish_entries.PublishEntry,
        'PublishEntry',
        # related_name="geoserver_channel",
        related_name="geoserver_channels",
        on_delete=models.CASCADE,
    )
    srs = models.CharField(null=True, blank=True, max_length=500)
    active = models.BooleanField(null=True, blank=True, default=True)  # When active=False, the layer on the geoserver will be deleted
    override_bbox = models.BooleanField(default=False)
    native_crs = models.CharField(null=True, blank=True, max_length=500)    # will become required, if overried_box is True
    nbb_minx = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    nbb_maxx = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    nbb_miny = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    nbb_maxy = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    nbb_crs = models.CharField(null=True, blank=True, max_length=500)   # will become required, if overried_box is True
    llb_minx = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    llb_maxx = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    llb_miny = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    llb_maxy = models.CharField(null=True, blank=True, max_length=500)  # will become required, if overried_box is True
    llb_crs = models.CharField(null=True, blank=True, max_length=500)   # will become required, if overried_box is True
    geoserver_pool = models.ForeignKey(  # We want to select the destination geoserver_pools rather than sending the layers to all the geoserver_pools.
        GeoServerPool,
        null=True, 
        blank=True,
        on_delete=models.SET_NULL,
    )
    store_type = models.IntegerField(choices=StoreType.choices, default=StoreType.GEOPACKAGE)
    # Cached layer
    create_cached_layer = models.BooleanField(default=True, blank=True)
    expire_server_cache_after_n_seconds = models.IntegerField(default=0, null=False, blank=False)  # meaningfull only if create_cached_layer is True
    expire_client_cache_after_n_seconds = models.IntegerField(default=0, null=False, blank=False)  # meaningfull only if create_cached_layer is True
    # GeoPackage Memory Map Size (MB)
    gpkg_memory_map_size = models.IntegerField(
        verbose_name="GeoPackage Memory Map Size (MB)",
        null=True,
        blank=True,
        help_text=(
            "Optional. The memory map size in Megabytes (MB) for this GeoPackage data store. "
            "Leave blank to use the GeoServer default."
        ),
        validators=[
            MinValueValidator(0)
        ]
    )

    objects = GeoServerPublishChannelManager()

    class Meta:
        """GeoServer Publish Channel Model Metadata."""
        verbose_name = "GeoServer Publish Channel"
        verbose_name_plural = "GeoServer Publish Channels"
        # unique_together = ('publish_entry', 'geoserver_pool',)

    def clean(self):
        if not self.override_bbox:
            return
        if self._has_null(self.native_crs, 
                           self.nbb_minx, self.nbb_maxx, self.nbb_miny, self.nbb_maxy, self.nbb_crs,
                           self.llb_minx, self.llb_maxx, self.llb_miny, self.llb_maxy, self.llb_crs):
            raise exceptions.ValidationError("If override_bbox is True, every related fields must be filled.")
        
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def _has_null(*args):
        for arg in args:
            if arg is None:
                return True
        return False
        
    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.id}: {self.publish_entry.name}"

    def perform_geoserver_layer_health_check(self):
        if not self.geoserver_pool or not self.geoserver_pool.enabled:
            return

        try:
            geoserver_obj = geoserverWithCustomCreds(self.geoserver_pool.url, self.geoserver_pool.username, self.geoserver_pool.password)

            try:
                response_data = geoserver_obj.get_layer_details(self.layer_name_with_workspace)  # Return value can be the layer details or None
                if response_data:
                    GeoServerLayerHealthcheck.objects.update_or_create(
                        geoserver_publish_channel=self,
                        layer_name=self.layer_name_with_workspace,
                        defaults={
                            'health_status': GeoServerLayerHealthcheck.HEALTHY,
                            'error_message': None,
                            'last_check_time': timezone.now()
                        }
                    )
                else:
                    raise Exception('response data is something wrong...')
            except Exception as e:
                GeoServerLayerHealthcheck.objects.update_or_create(
                    geoserver_publish_channel=self,
                    layer_name=self.layer_name_with_workspace,
                    defaults={
                        'health_status': GeoServerLayerHealthcheck.UNHEALTHY,
                        'error_message': str(e),
                        'last_check_time': timezone.now()
                    }
                )
        except Exception as e:
            GeoServerLayerHealthcheck.objects.update_or_create(
                geoserver_publish_channel=self,
                layer_name='all_layers',
                defaults={
                    'health_status': GeoServerLayerHealthcheck.UNHEALTHY,
                    'error_message': str(e),
                    'last_check_time': timezone.now()
                }
            )

    @property
    def name(self) -> str:
        return self.publish_entry.name

    @property
    def layer_name_with_workspace(self) -> str:
        if self.workspace:
            return f"{self.workspace.name}:{self.name}"
        return self.name

    def publish(self, symbology_only: bool = False) -> None:
        """Publishes the Catalogue Entry to this channel if applicable.

        Args:
            symbology_only (bool): Whether to publish symbology only.
        """
        # Log
        log.info(f"Attempting to publish [{self.publish_entry}] to the geoserver: [{self.geoserver_pool.url}]...")

        geoserver_obj = geoserverWithCustomCreds(self.geoserver_pool.url, self.geoserver_pool.username, self.geoserver_pool.password)

        # Publish Symbology
        self.publish_geoserver_symbology(geoserver=geoserver_obj)

        # Check Symbology Only Flag
        if symbology_only:
            log.info(f"Skipping publishing layer due to {symbology_only=}")
            return

        self.publish_geoserver_layer(geoserver=geoserver_obj)

        # Update Published At
        publish_time = timezone.now()
        self.publish_entry.published_at = publish_time
        self.publish_entry.save()
        self.published_at = publish_time
        self.save()

    def publish_geoserver_symbology(self, geoserver: gis.geoserver.GeoServer) -> None:
        """Publishes the Symbology to GeoServer if applicable."""
        # Log
        log.info(f"Attempting to publish the style of the CatalogueEntry: [{self.publish_entry.catalogue_entry}] to GeoServer: [{geoserver.service_url}]...")

        if hasattr(self.publish_entry.catalogue_entry, 'symbology'):
            # Publish Style to GeoServer
            symbology = self.publish_entry.catalogue_entry.symbology
            log.info(f'Symbology: [{symbology}] found in the CatalogueEntry: [{self.publish_entry.catalogue_entry}]')

            style_uploaded = geoserver.upload_style(
                workspace=self.workspace.name,
                style_name=symbology.name,
                new_sld=symbology.sld,
                use_raw=symbology.use_raw
            )
            # if style_uploaded:
            #     # geoserver.set_style_to_layer(
            #     #     self.publish_entry.catalogue_entry.name,
            #     #     self.publish_entry.catalogue_entry.symbology.name
            #     # )
            #     geoserver.set_default_style_to_layer(
            #         self.publish_entry.catalogue_entry.symbology.name,
            #         self.workspace.name,
            #         self.publish_entry.catalogue_entry.name
            #     )
        else:
            log.info(f'CatalogueEntry: [{self.publish_entry.catalogue_entry}] does not have Symbology.')

    def publish_geoserver_layer(self, geoserver: gis.geoserver.GeoServer) -> None:
        """Publishes the Catalogue Entry to GeoServer if applicable.

        Args:
            wms (bool): Whether to enable WMS capabilities.
            wfs (bool): Whether to enable WFS capabilities.
        """
        # Log
        log.info(f"Publishing '[{self.publish_entry.catalogue_entry}]' (Layer) to the GeoServer: [{geoserver.service_url}]...")
        
        if not self.publish_entry.catalogue_entry.active_layer:
            msg = f'CatalogueEntry: [{self.publish_entry.catalogue_entry}] does not have an active_layer.  Nothing to publish.'
            log.error(msg)
            raise FileNotFoundError(msg)

        filepath = pathlib.Path(self.publish_entry.catalogue_entry.active_layer.file) 
 
        if self.store_type == StoreType.GEOPACKAGE:
            # Convert Layer to GeoPackage
            geopackage = gis.conversions.to_geopackage(
                filepath=filepath,
                layer=self.publish_entry.catalogue_entry.metadata.name,
                catalogue_name=self.publish_entry.catalogue_entry.name,
                export_method='geoserver'
            )
                
            # Push Layer to GeoServer
            geoserver.upload_geopackage(
                workspace=self.workspace.name,
                layer=self.publish_entry.catalogue_entry.metadata.name,
                filepath=geopackage['full_filepath'],
            )
        elif self.store_type == StoreType.GEOTIFF:
            workspace_name = self.workspace.name
            layer_name = self.publish_entry.catalogue_entry.metadata.name
            geoserver.upload_tif(
                workspace=workspace_name,
                layer=layer_name,
                filepath=filepath,
            )
            # Once uploaded, create a layer for the coverage store
            geoserver.create_layer_from_coveragestore(workspace_name, layer_name)
        else:
            log.warning(f'Unknown store_type: [{self.store_type}].')

        # Set Style to the layer
        style_name = self.publish_entry.catalogue_entry.symbology.name if hasattr(self.publish_entry.catalogue_entry, 'symbology') and self.publish_entry.catalogue_entry.symbology.name and self.publish_entry.catalogue_entry.symbology.sld else 'generic'
        geoserver.set_default_style_to_layer(
            style_name=style_name,
            workspace_name=self.workspace.name,
            layer_name=self.publish_entry.catalogue_entry.metadata.name,
        )


@reversion.register()
class FTPServer(mixins.RevisionedMixin):
    """Model for a GeoServer Publish Channel."""
    name = models.CharField(null=True, blank=True, max_length=1024)
    host = models.CharField(null=True, blank=True, max_length=1024)
    username = models.CharField(null=True, blank=True, max_length=500)
    password = models.CharField(null=True, blank=True, max_length=500)
    enabled = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


@reversion.register()
class FTPPublishChannel(mixins.RevisionedMixin):
    """Model for a GeoServer Publish Channel."""
    name = models.CharField(null=True, blank=True, max_length=1024)
    ftp_server = models.ForeignKey(
        FTPServer,
        related_name="publish_channels_ftp_server",
        on_delete=models.CASCADE,
        null=True, 
        blank=True,
    )  
    publish_entry = models.ForeignKey(
        # publish_entries.PublishEntry,
        'PublishEntry',
        related_name="ftp_channels",
        on_delete=models.CASCADE,
        null=True, 
        blank=True,        
    )
    format = models.IntegerField(choices=FTPPublishChannelFormat.choices) 
    frequency = models.IntegerField(choices=PublishChannelFrequency.choices)
    path = models.CharField(null=True, blank=True, max_length=2048)
    published_at = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name
    

    def publish(self, symbology_only: bool = False) -> None:
        """Publishes the Catalogue Entry to this channel if applicable.

        Args:
            symbology_only (bool): Whether to publish symbology only.
        """
        # Log
        log.info(f"Attempting to ftp publish '{self.publish_entry}' to channel '{self}'")

        # Check Symbology Only Flag
        if symbology_only:
            # Log
            log.info(f"Skipping due to {symbology_only=}")

            # Exit Early
            return

        self.publish_ftp()
        
        # Update Published At
        publish_time = timezone.now()
        self.publish_entry.published_at = publish_time
        self.publish_entry.save()
        self.published_at = publish_time
        self.save()

    def publish_ftp(self) -> None:
        """Publishes the Catalogue Entry to FTP. """
        # Log
        log.info(f"Publishing '{self}' to FTP - Preparing")
        
        # Retrieve the Layer File from Storage
        # filepath = sharepoint.sharepoint_input().get_from_url(
        #     url=self.publish_entry.catalogue_entry.active_layer.file,
        # )
        filepath = pathlib.Path(self.publish_entry.catalogue_entry.active_layer.file)        

        # Select Conversion Function
        match self.format:
            case CDDPPublishChannelFormat.GEOPACKAGE:
                function = gis.conversions.to_geopackage
            case CDDPPublishChannelFormat.SHAPEFILE:
                function = gis.conversions.to_shapefile
            case CDDPPublishChannelFormat.GEODATABASE:
                function = gis.conversions.to_geodatabase
            case CDDPPublishChannelFormat.GEOJSON:
                function = gis.conversions.to_geojson

        t = Template(self.name)
        c = Context({"date_time": datetime.now()})
        generated_template = t.render(c)     
        log.info(f"Publishing '{self}' to FTP - Converting")
        publish_directory = function(
            filepath=filepath,
            layer=generated_template,
            catalogue_name=self.publish_entry.catalogue_entry.name,
            export_method='ftp'
        )
        
        log.info(f"Publishing '{self}' to FTP - Uploading to FTP "+(self.path + os.path.sep + generated_template) + '.zip' )
        session = ftplib.FTP(self.ftp_server.host,self.ftp_server.username,self.ftp_server.password)
        file = open(publish_directory['compressed_filepath'],'rb')     
        session.storbinary('STOR '+str(self.path + os.path.sep + generated_template) + '.zip', file)
        file.close()  
        session.quit()


class GeoServerLayerHealthcheck(mixins.RevisionedMixin):
    HEALTHY = 'healthy'
    UNHEALTHY = 'unhealthy'
    UNKNOWN = 'unknown'

    HEALTH_CHOICES = [
        (HEALTHY, 'Healthy'),
        (UNHEALTHY, 'Unhealthy'),
        (UNKNOWN, 'Unknown'),
    ]

    geoserver_publish_channel = models.ForeignKey(
        GeoServerPublishChannel,
        on_delete=models.CASCADE,
        related_name='health_checks'
    )
    layer_name = models.CharField(max_length=255)  # layer_name could be retrieved from the geoserver_publish_channel
    health_status = models.CharField(max_length=20, choices=HEALTH_CHOICES, default=UNKNOWN)
    last_check_time = models.DateTimeField()
    error_message = models.TextField(blank=True, null=True)
