"""Kaartdijin Boodja Publisher Django Application Filters."""


# Third-Party
from django_filters import rest_framework as filters

# Local
from govapp.apps.publisher import models


class CDDPPublishChannelFilter(filters.FilterSet):
    """CDDP Publish Channel Filter."""
    class Meta:
        """CDDP Publish Channel Filter Metadata."""
        model = models.publish_channels.CDDPPublishChannel
        fields = {"id": ["in"]}

class FTPPublishChannelFilter(filters.FilterSet):
    """FTP Publish Channel Filter."""
    class Meta:
        """FTP Publish Channel Filter Metadata."""
        model = models.publish_channels.FTPPublishChannel
        fields = {"id": ["in"]}

class FTPServerFilter(filters.FilterSet):
    """FTP Server Filter."""
    class Meta:
        """FTP Server Filter Metadata."""
        model = models.publish_channels.FTPServer
        fields = {"id": ["in"]}

class GeoServerPublishChannelFilter(filters.FilterSet):
    """GeoServer Publish Channel Filter."""
    class Meta:
        """GeoServer Publish Channel Filter Metadata."""
        model = models.publish_channels.GeoServerPublishChannel
        fields = {"id": ["in"], "workspace": ["exact"], "geoserver_pool": ["exact"]}


class PublishEntryFilter(filters.FilterSet):
    """Publish Entry Filter."""
    updated = filters.IsoDateTimeFromToRangeFilter(field_name="updated_at")
    published = filters.IsoDateTimeFromToRangeFilter(field_name="published_at")
    order_by = filters.OrderingFilter(
        fields=(
            "id",
            ("catalogue_entry__name", "name"),  # Proxy through the Catalogue Entry name to sort by
            "status",
            "updated_at",
            "published_at",
            "assigned_to",
            ("catalogue_entry__custodian__name", "custodian"),
        )
    )

    class Meta:
        """Publish Entry Filter Metadata."""
        model = models.publish_entries.PublishEntry
        fields = {"id": ["exact", "in"], "assigned_to": ["exact"], "status": ["exact"], 
                  "catalogue_entry__name": ["icontains", "contains"], 
                  "description": ["icontains", "contains"], 
                  "catalogue_entry__custodian": ["exact"]  }
        #fields = {"name": ['contains'] }


class EmailNotificationFilter(filters.FilterSet):
    """Email Notification Filter."""
    order_by = filters.OrderingFilter(fields=("id", "name", "type", "email", "active"))
    
    class Meta:
        """Email Notification Filter Metadata."""
        model = models.notifications.EmailNotification
        fields = {"id": ["in"], "publish_entry":["exact"]}


class WorkspaceFilter(filters.FilterSet):
    """Workspace Filter."""
    class Meta:
        """Workspace Filter Metadata."""
        model = models.workspaces.Workspace
        fields = ()
