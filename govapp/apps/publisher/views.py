"""Kaartdijin Boodja Publisher Django Application Views."""


# Third-Party
import os
import logging
from datetime import datetime
from django import shortcuts
from django.db import transaction
from django.db.models import Q
from django.contrib import auth
from django import http
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from drf_spectacular import utils as drf_utils
from rest_framework import decorators
from rest_framework import request
from rest_framework import response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import filters as rest_filters
from rest_framework_datatables.pagination import DatatablesPageNumberPagination
from rest_framework_datatables.renderers import DatatablesRenderer
from rest_framework.renderers import JSONRenderer
# Local
from govapp import settings
from govapp.apps.accounts.serializers import UserSerializer
from govapp.apps.accounts.utils import get_file_list
from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerGroup, GeoServerGroupUser, GeoServerRole
from govapp.apps.publisher.serializers.geoserver_group import GeoServerGroupSerializer, GeoServerRoleSerializer
from govapp.common import mixins
from govapp.common import utils
from govapp.apps.accounts import permissions as accounts_permissions
from govapp.apps.logs import mixins as logs_mixins
from govapp.apps.logs import utils as logs_utils
from govapp.apps.publisher import filters
from govapp.apps.publisher import models
from govapp.apps.publisher import permissions
from govapp.apps.publisher import serializers
from govapp.apps.publisher import geoserver_manager
from govapp.apps.publisher.models.geoserver_queues import GeoServerQueueStatus
from govapp.apps.publisher.models.geoserver_layer_groups import GeoServerLayerGroup
from govapp.apps.publisher.serializers.geoserver_layer_group import GeoServerLayerGroupSerializer
from govapp.apps.publisher import geoserver_layergroup_publisher

# Typing
from typing import cast, Any


# Shortcuts
UserModel = auth.get_user_model()

# Log
log = logging.getLogger('__name__')


@drf_utils.extend_schema(tags=["Publisher - Publish Entries"])
class PublishEntryViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    logs_mixins.ActionsLogMixin,
    logs_mixins.CommunicationsLogMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Publish Entry View Set."""
    queryset = models.publish_entries.PublishEntry.objects.all()
    serializer_class = serializers.publish_entries.PublishEntrySerializer
    serializer_classes = {"create": serializers.publish_entries.PublishEntryCreateSerializer}
    filterset_class = filters.PublishEntryFilter
    search_fields = ["description", "catalogue_entry__name"]
    permission_classes = [permissions.IsPublishEntryPermissions]

    def list(self, request, *args, **kwargs):
        """Api to return a list of publish entry
            Convert date format of updated_at to %d %b %Y %H:%M %p

        Args:
            request (_type_): request object passed by Django framework

        Returns:
            response.Response: a full list of publish entry
        """
        response = super().list(request, *args, **kwargs)
        for result in response.data.get('results'):
            if result.get('updated_at'):
                date_obj = datetime.strptime(result.get('updated_at'), "%Y-%m-%dT%H:%M:%S.%f%z")
                result['updated_at'] = str(date_obj.astimezone().strftime('%d %b %Y %H:%M %p'))
                 
        return response

    def perform_create(self, serializer):
        publish_entry = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=publish_entry,
            action=f"PublishEntry: [{publish_entry}] has been created with the data: [{serializer.data}]."
        )
        log.info(f"PublishEntry: [{publish_entry}] has been created with the data: [{serializer.data}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        publish_entry = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=publish_entry,
            action=f"PublishEntry: [{publish_entry}] has been updated with the data: [{serializer.data}]."
        )
        log.info(f"PublishEntry: [{publish_entry}] has been updated with the data: [{serializer.data}] by the user: [{self.request.user}].")

    # def update(self, request, *args, **kwargs):
    #     ret = super(PublishEntryViewSet, self).update(request, *args, **kwargs)

    #     publish_entry = self.get_object()
    #     logs_utils.add_to_actions_log(
    #         user=request.user,
    #         model=publish_entry,
    #         action=f"PublishEntry: [{publish_entry}] has been updated with the data: [{request.data}]."
    #     )
    #     log.info(f"PublishEntry: [{publish_entry}] has been updated with the data: [{request.data}] by the user: [{request.user}].")

    #     return ret
    
    @drf_utils.extend_schema(
        parameters=[drf_utils.OpenApiParameter("symbology_only", type=bool)],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    @decorators.action(detail=True, methods=["POST"])
    def publish(self, request: request.Request, pk: str) -> response.Response:
        """Publishes to both channels.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Retrieve `symbology_only` Query Parameter
        symbology_only = self.request.query_params.get("symbology_only")
        symbology_only = utils.string_to_boolean(symbology_only)  # type: ignore[assignment]

        # Publish!
        publish_entry.publish(symbology_only)

        # Add Action Log Entry
        logs_utils.add_to_actions_log(
            user=request.user,
            model=publish_entry,
            action=f"PublishEntry: [{publish_entry}] has been manually re-published to all the channels."
        )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(
        parameters=[drf_utils.OpenApiParameter("symbology_only", type=bool)],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    @decorators.action(detail=True, methods=["POST"], url_path=r"publish/cddp")
    def publish_cddp(self, request: request.Request, pk: str) -> response.Response:
        """Publishes to the CDDP Channel.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Retrieve `symbology_only` Query Parameter
        symbology_only = self.request.query_params.get("symbology_only")
        symbology_only = utils.string_to_boolean(symbology_only)  # type: ignore[assignment]

        # Publish!
        publish_entry.publish_cddp(symbology_only)

        # Add Action Log Entry
        logs_utils.add_to_actions_log(
            user=request.user,
            model=publish_entry,
            action=f"PublishEntry: [{publish_entry}] has been manually re-published to the CDDP channel."
        )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic()
    @drf_utils.extend_schema(
        parameters=[drf_utils.OpenApiParameter("symbology_only", type=bool)],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    @decorators.action(detail=True, methods=["POST"], url_path=r"publish/geoserver")
    def publish_geoserver(self, request: request.Request, pk: str) -> response.Response:
        """Publishes to the GeoServer Channel.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Retrieve `symbology_only` Query Parameter
        symbology_only = self.request.query_params.get("symbology_only")
        symbology_only = utils.string_to_boolean(symbology_only)  # type: ignore[assignment]

        # already exists
        if publish_entry.geoserver_queues.filter(
            status__in=[GeoServerQueueStatus.READY, GeoServerQueueStatus.PROCESSING]).exists():
            return response.Response(status=status.HTTP_409_CONFLICT)
        else:
            # creating a queue item when it doesn't exist
            res = geoserver_manager.push(publish_entry=publish_entry, 
                                               symbology_only=symbology_only, 
                                               submitter=request.user)
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action=f"PublishEntry: [{publish_entry}] has been manually pushed to the GeoServerQueue."
            )
        if res:
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        else :
            return response.Response(status=status.HTTP_412_PRECONDITION_FAILED)


    @drf_utils.extend_schema(
        parameters=[drf_utils.OpenApiParameter("symbology_only", type=bool)],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None},
    )
    @decorators.action(detail=True, methods=["POST"], url_path=r"publish/ftp")
    def publish_ftp(self, request: request.Request, pk: str) -> response.Response:
        """Publishes to the FTP.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Retrieve `symbology_only` Query Parameter
        symbology_only = self.request.query_params.get("symbology_only")
        symbology_only = utils.string_to_boolean(symbology_only)  # type: ignore[assignment]

        # Publish!
        publish_entry.publish_ftp(symbology_only)

        # Add Action Log Entry
        logs_utils.add_to_actions_log(
            user=request.user,
            model=publish_entry,
            action="Publish entry was manually re-published to the FTP channel"
        )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=True, methods=["GET"], url_path=r"geoserver")
    def geoserver_list(self, request: request.Request, pk: str) -> response.Response:
        """Produce a list of GeoServer publish configurations

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # # Retrieve Publish Entry
        # # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)
        geoserver_publish_channel = models.publish_channels.GeoServerPublishChannel.objects.filter(publish_entry=publish_entry).order_by('id')
        serializer = serializers.publish_channels.GeoServerPublishChannelSerializer(geoserver_publish_channel, many=True)
        
        # Return Response
        return response.Response(serializer.data, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["GET"], url_path=r"cddp")
    def cddp_list(self, request: request.Request, pk: str) -> response.Response:
        """Produce a list of CDDP publish configurations

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)
        cddp_publish_channels = models.publish_channels.CDDPPublishChannel.objects.filter(publish_entry=publish_entry)
        cddp_list = []

        cddp_data = {
            'cddp_user_path': settings.CDDP_USER_PATH,
            'cddp_publish_entries_list': []
        }

        for cddp_publish_channel in cddp_publish_channels:
            published_at = None
            
            if cddp_publish_channel.published_at:
                published_at = cddp_publish_channel.published_at.astimezone().strftime('%d %b %Y %H:%M %p')
            
            if os.path.isabs(cddp_publish_channel.path):
                cddp_publish_channel.path = os.path.relpath(cddp_publish_channel.path, start="/")
            # combined_path = os.path.join(settings.CDDP_USER_PATH, cddp_publish_channel.path)
                 
            # cddp_list.append({
            cddp_data['cddp_publish_entries_list'].append({
                "id": cddp_publish_channel.id, 
                "name":cddp_publish_channel.name, 
                "format": cddp_publish_channel.format, 
                "path": cddp_publish_channel.path,
                "cddp_user_path": settings.CDDP_USER_PATH,
                "mode": cddp_publish_channel.mode, 
                "frequency": cddp_publish_channel.frequency, 
                "published_at": published_at,
                "xml_path":cddp_publish_channel.xml_path
            })

        # Return Response
        # return response.Response(cddp_list, status=status.HTTP_200_OK)
        return response.Response(cddp_data, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["GET"], url_path=r"ftp")
    def ftp_list(self, request: request.Request, pk: str) -> response.Response:
        """Produce a list of FTP publish configurations

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)
        ftp_publish_channel = models.publish_channels.FTPPublishChannel.objects.filter(publish_entry=publish_entry)
        ftp_list = []
        for cpc in ftp_publish_channel:
            published_at = None
            
            if cpc.published_at:
                 published_at = cpc.published_at.astimezone().strftime('%d %b %Y %H:%M %p')  
            ftp_server_id = ""
            ftp_server_name = ""
                                              
            if cpc.ftp_server:
                ftp_server_id = cpc.ftp_server.id
                ftp_server_name = cpc.ftp_server.name
                             
            ftp_list.append({"id": cpc.id, "name":cpc.name, "ftp_server_id": ftp_server_id, "ftp_server_name" : ftp_server_name, "format": cpc.format, "path": cpc.path, "frequency": cpc.frequency, "published_at": published_at})

        # Return Response
        return response.Response(ftp_list, status=status.HTTP_200_OK)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def lock(self, request: request.Request, pk: str) -> response.Response:
        """Locks the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Lock
        success = publish_entry.lock()

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action=f"Publish entry: [{publish_entry}] has been locked."
            )
            log.info(f"Publish entry: [{publish_entry}] has been locked by the user: [{request.user}].")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses=serializers.publish_entries.PublishEntryCreateEditorSerializer)
    @decorators.action(detail=True, methods=["POST"], url_path=r"editors/add/(?P<user_pk>\d+)")
    def add_editors(self, request: request.Request, pk: str, user_pk: str) -> response.Response:
        """Unlocks the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Add Editor to Publish
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)
        user = UserModel.objects.get(id=user_pk)
        publish_entry.editors.add(user)

        success = False
        editors = publish_entry.editors.all()
        if user in editors:
            success = True

        #Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action="Publish entry add editor {} with id {} ".format(user.first_name+' '+user.last_name, user_pk)
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses=serializers.publish_entries.PublishEntryListEditorSerializer)
    @decorators.action(detail=True, methods=["GET"], url_path=r"editors")
    def editors(self, request: request.Request, pk: str) -> response.Response:
        """Unlocks the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry        
        publish_entry = self.get_object()
        editors = publish_entry.editors.all()
        editors_list = []
        for e in editors:
            editors_list.append({'id': e.id,'first_name' : e.first_name,'last_name' : e.last_name, 'email': e.email})

        # Return Response
        return response.Response(editors_list, status=status.HTTP_200_OK)

    @drf_utils.extend_schema(request=None, responses=serializers.publish_entries.PublishEntryCreateEditorSerializer)
    @decorators.action(detail=True, methods=["DELETE"], url_path=r"editors/delete/(?P<user_pk>\d+)")
    def delete_editors(self, request: request.Request, pk: str, user_pk: str) -> response.Response:
        """Unlocks the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)
        user = UserModel.objects.get(id=user_pk)
        success = publish_entry.editors.remove(user)
        success = False
        editors = publish_entry.editors.all()
        if user not in editors:
            success = True
   
        #Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action="Publish entry delete editor {} with id {} ".format(user.first_name+' '+user.last_name, user_pk)
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def unlock(self, request: request.Request, pk: str) -> response.Response:
        """Unlocks the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Unlock
        success = publish_entry.unlock()

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action=f"Publish entry: [{publish_entry}] has been unlocked."
            )
            log.info(f"Publish entry: [{publish_entry}] has been unlocked by the user: [{request.user}].")

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"], url_path=r"assign/(?P<user_pk>\d+)")
    def assign(self, request: request.Request, pk: str, user_pk: str) -> response.Response:
        """Assigns the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.
            user_pk (str): Primary key of the User to assign to.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Retrieve User
        user = shortcuts.get_object_or_404(UserModel, id=user_pk)

        # Assign!
        success = publish_entry.assign(user)

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action=f"Publish entry has been assigned to the user: [{user} (id: {user.pk})]."
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def unassign(self, request: request.Request, pk: str) -> response.Response:
        """Unassigns the Publish Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Publish Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Publish Entry
        # Help `mypy` by casting the resulting object to a Publish Entry
        publish_entry = self.get_object()
        publish_entry = cast(models.publish_entries.PublishEntry, publish_entry)

        # Unassign!
        success = publish_entry.unassign()

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=publish_entry,
                action="Publish entry was unassigned"
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)


@drf_utils.extend_schema(tags=["Publisher - CDDP Publish Channels"])
class CDDPPublishChannelViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """CDDP Publish Channel View Set."""
    queryset = models.publish_channels.CDDPPublishChannel.objects.all()
    serializer_class = serializers.publish_channels.CDDPPublishChannelSerializer
    serializer_classes = {"create": serializers.publish_channels.CDDPPublishChannelCreateSerializer}
    filterset_class = filters.CDDPPublishChannelFilter
    search_fields = ["publish_entry__catalogue_entry__name",]# "publish_entry__description"]
    permission_classes = [permissions.HasPublishEntryPermissions]

    def perform_create(self, serializer):
        cddp_publish_channel = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model= cddp_publish_channel.publish_entry,
            action=f"CDDPPublishChannel: [{cddp_publish_channel}] has been created with the data: [{serializer.data}]."
        )
        log.info(f"CDDPPublishChannel: [{cddp_publish_channel}] has been created with the data: [{serializer.data}] from this PublishEntry: [{cddp_publish_channel.publish_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        cddp_publish_channel = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=cddp_publish_channel.publish_entry,
            action=f"CDDPPublishChannel: [{cddp_publish_channel}] has been updated with the data: [{serializer.data}]."
        )
        log.info(f"CDDPPublishChannel: [{cddp_publish_channel}] has been updated with the data: [{serializer.data}] from the PublishEntry: [{cddp_publish_channel.publish_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        publish_entry = instance.publish_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=publish_entry,
            action=f"CDDPPublishChannel: [{instance}] has been deleted."
        )
        log.info(f"CDDPPublishChannel: [{instance}] has been deleted from the PublishEntry: [{publish_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)


@drf_utils.extend_schema(tags=["Publisher - GeoServer Publish Channels"])
class GeoServerPublishChannelViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """GeoServer Publish Channel View Set."""
    queryset = models.publish_channels.GeoServerPublishChannel.objects.all()
    serializer_class = serializers.publish_channels.GeoServerPublishChannelSerializer
    serializer_classes = {"create": serializers.publish_channels.GeoServerPublishChannelCreateSerializer}
    filterset_class = filters.GeoServerPublishChannelFilter
    search_fields = ["publish_entry__catalogue_entry__name", "publish_entry__description"]
    permission_classes = [permissions.HasPublishEntryPermissions]

    def perform_create(self, serializer):
        geoserver_publish_channel = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model= geoserver_publish_channel.publish_entry,
            action=f"GeoServerPublishChannel: [{geoserver_publish_channel}] has been created with the data: [{serializer.data}]."
        )
        log.info(f"GeoServerPublishChannel: [{geoserver_publish_channel}] has been created with the data: [{serializer.data}] from this PublishEntry: [{geoserver_publish_channel.publish_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        geoserver_publish_channel = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=geoserver_publish_channel.publish_entry,
            action=f"GeoServerPublishChannel: [{geoserver_publish_channel}] has been updated with the data: [{serializer.data}]."
        )
        log.info(f"GeoServerPublishChannel: [{geoserver_publish_channel}] has been updated with the data: [{serializer.data}] from the PublishEntry: [{geoserver_publish_channel.publish_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        publish_entry = instance.publish_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=publish_entry,
            action=f"GeoServerPublishChannel: [{instance}] has been deleted."
        )
        log.info(f"GeoServerPublishChannel: [{instance}] has been deleted from the PublishEntry: [{publish_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)


@drf_utils.extend_schema(tags=["Publisher - Notifications (Email)"])
class EmailNotificationViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Email Notification View Set."""
    queryset = models.notifications.EmailNotification.objects.all()
    serializer_class = serializers.notifications.EmailNotificationSerializer
    serializer_classes = {"create": serializers.notifications.EmailNotificationCreateSerializer}
    filterset_class = filters.EmailNotificationFilter
    search_fields = ["name", "email"]
    permission_classes = [permissions.HasPublishEntryPermissions | accounts_permissions.IsInAdministratorsGroup]
    
    # to pass the pk to serializer
    def get_serializer_context(self):
        context = super().get_serializer_context()
        if context['request'].method == 'PUT':
            context['pk'] = self.kwargs['pk']
        return context

    def perform_create(self, serializer):
        email_notification = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model= email_notification.publish_entry,
            action=f"EmailNotification: [{email_notification}] has been created with the data: [{serializer.data}]."
        )
        log.info(f"EmailNotification: [{email_notification}] has been created with the data: [{serializer.data}] from this PublishEntry: [{email_notification.publish_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        email_notification = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=email_notification.publish_entry,
            action=f"EmailNotification: [{email_notification}] has been updated with the data: [{serializer.data}]."
        )
        log.info(f"EmailNotification: [{email_notification}] has been updated with the data: [{serializer.data}] from the PublishEntry: [{email_notification.publish_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        publish_entry = instance.publish_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=publish_entry,
            action=f"EmailNotification: [{instance}] has been deleted."
        )
        log.info(f"EmailNotification: [{instance}] has been deleted from the PublishEntry: [{publish_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)


@drf_utils.extend_schema(tags=["Publisher - Workspaces"])
class WorkspaceViewSet(mixins.ChoicesMixin, viewsets.ReadOnlyModelViewSet):
    """Workspace View Set."""
    queryset = models.workspaces.Workspace.objects.all()
    serializer_class = serializers.workspaces.WorkspaceSerializer
    filterset_class = filters.WorkspaceFilter
    search_fields = ["name"]




@drf_utils.extend_schema(tags=["Publisher - FTP Publish Channels"])
class FTPPublishChannelViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """FTP Publish Channel View Set."""
    queryset = models.publish_channels.FTPPublishChannel.objects.all()
    serializer_class = serializers.publish_channels.FTPPublishChannelSerializer
    serializer_classes = {"create": serializers.publish_channels.FTPPublishChannelCreateSerializer}
    filterset_class = filters.FTPPublishChannelFilter
    search_fields = ["publish_entry__catalogue_entry__name",]# "publish_entry__description"]
    permission_classes = [permissions.HasPublishEntryPermissions]

    # def update(self, request, *args, **kwargs):
    #     return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        ftp_publish_channel = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model= ftp_publish_channel.publish_entry,
            action=f"FTPPublishChannel: [{ftp_publish_channel}] has been created with the data: [{serializer.data}]."
        )
        log.info(f"FTPPublishChannel: [{ftp_publish_channel}] has been created with the data: [{serializer.data}] from this PublishEntry: [{ftp_publish_channel.publish_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        ftp_publish_channel = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=ftp_publish_channel.publish_entry,
            action=f"FTPPublishChannel: [{ftp_publish_channel}] has been updated with the data: [{serializer.data}]."
        )
        log.info(f"FTPPublishChannel: [{ftp_publish_channel}] has been updated with the data: [{serializer.data}] from the PublishEntry: [{ftp_publish_channel.publish_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        publish_entry = instance.publish_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=publish_entry,
            action=f"FTPPublishChannel: [{instance}] has been deleted."
        )
        log.info(f"FTPPublishChannel: [{instance}] has been deleted from the PublishEntry: [{publish_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)


@drf_utils.extend_schema(tags=["Publisher - FTP Publish Channels"])
class FTPServerViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """FTP Publish Channel View Set."""
    queryset = models.publish_channels.FTPServer.objects.all()
    serializer_class = serializers.publish_channels.FTPServerSerializer
    #serializer_classes = {"create": serializers.publish_channels.FTPPublishChannelCreateSerializer}
    serializer_classes = {}
    filterset_class = filters.FTPServerFilter
    search_fields = ["id","name",]# "publish_entry__description"]
    permission_classes = [permissions.HasPublishEntryPermissions]    
    
@drf_utils.extend_schema(tags=["Publisher - GeoServer Queues"])
class GeoServerQueueViewSet(
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """GeoServer Queue View Set."""
    queryset = models.geoserver_queues.GeoServerQueue.objects.all().order_by('-id')
    serializer_class = serializers.publish_channels.GeoServerQueueSerializer
    permission_classes = [accounts_permissions.IsInAdministratorsGroup]


class CsrfExemptSessionAuthentication(SessionAuthentication):

    def enforce_csrf(self, request):
        return  # To not perform the csrf check previously happening
    

class CDDPContentsViewSet(
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    ViewSet for handling files within a specified directory.
    Provides list, retrieve, and delete functionalities.
    """
    permission_classes=[accounts_permissions.CanAccessCDDP,]
    pathToFolder = settings.AZURE_OUTPUT_SYNC_DIRECTORY
    authentication_classes = [CsrfExemptSessionAuthentication, BasicAuthentication,]

    def enforce_csrf(self, *args, **kwargs):
        '''
        Bypass the CSRF checks altogether
        '''
        pass 

    def list(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """
        List all files within the directory along with their metadata.
        """
        try:
            limit = request.GET.get('limit', None)
            offset = request.GET.get('offset', 0)
            order_by = request.GET.get('order_by', 'created_at')

            results = self._get_files_with_metadata(limit, offset, order_by)
            return Response(results)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _get_files_with_metadata(self, limit, offset, order_by) -> list:
        """
        Retrieve file paths and metadata for files within the specified directory.
        """

        try:
            file_list, num_of_files = get_file_list(self.pathToFolder)

            reverse = order_by.startswith('-')
            key = order_by.lstrip('-')
            file_list.sort(key=lambda x: x.get(key, None), reverse=reverse)
            
            # Offset
            offset = int(offset)
            file_list = file_list[offset:]
            
            # limit
            if limit:
                limit = int(limit)
                file_list = file_list[:limit]

            return {
                'count': num_of_files,
                'results': file_list
            }

        except Exception as e:
            raise RuntimeError(f"Error while retrieving file metadata: {str(e)}")

    @decorators.action(detail=False, methods=['get'], url_path='retrieve-file')
    def retrieve_file(self, request: http.HttpRequest) -> http.HttpResponse:
        """
        Retrieve the specified file's content.

        Usage:
        Make a GET request to the '/retrieve-file' endpoint and provide the 'filepath' as a query parameter.
        Example: /api/publish/cddp-contents/retrieve-file?filepath=path/to/file.txt

        Parameters:
        - filepath: The path of the file to retrieve.
        """
        filepath = request.query_params.get('filepath')
        log.info(f'Retrieving file: [{filepath}]')

        if not filepath:
            log.error('Filepath query parameter is required')
            return Response({'error': 'Filepath query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        filepath = os.path.join(self.pathToFolder, filepath)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as file:
                    # Create the response with the file content and set the appropriate headers
                    response = http.HttpResponse(file.read(), content_type='application/octet-stream')
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(filepath)}"'
                    return response
            except Exception as e:
                log.error(f'Error retrieving file [{filepath}]: [{str(e)}]')
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            log.error(f'File does not exist: [{filepath}]')
            raise http.Http404("File does not exist")

    @decorators.action(detail=False, methods=['delete'], url_path='delete-file')
    def destroy_file(self, request: http.HttpRequest) -> http.HttpResponse:
        """
        Delete the specified file.

        Usage:
        Make a DELETE request to the '/destroy-file' endpoint and provide the 'filepath' as a query parameter.
        Example: /api/publish/cddp-contents/destroy-file?filepath=path/to/file.txt

        Parameters:
        - filepath: The path of the file to delete.
        """
        filepath = request.query_params.get('filepath')
        log.info(f'Deleting file: [{filepath}]')

        if not filepath:
            log.error('Filepath query parameter is required')
            return Response({'error': 'Filepath query parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        filepath = os.path.join(self.pathToFolder, filepath)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                log.info(f'File [{filepath}] deleted successfully')

                # Check if the directory is empty
                dirpath = os.path.dirname(filepath)
                if not os.listdir(dirpath) and dirpath != self.pathToFolder:
                    os.rmdir(dirpath)
                    log.info(f'Directory [{dirpath}] deleted successfully')

                return Response(status=status.HTTP_204_NO_CONTENT)
            except Exception as e:
                log.error(f'Error deleting file [{filepath}]: {str(e)}')
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            log.error(f'File does not exist: [{filepath}]')
            raise http.Http404("File does not exist")


from rest_framework_datatables.pagination import DatatablesPageNumberPagination
from rest_framework_datatables.filters import DatatablesFilterBackend


class CustomPageNumberPagination(DatatablesPageNumberPagination):
    page_size_query_param = 'length'
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            'draw': int(self.request.query_params.get('draw', 1)),
            'recordsTotal': self.page.paginator.count,
            'recordsFiltered': self.page.paginator.count,
            'data': data
        })


class GeoServerGroupViewSet(
        viewsets.mixins.ListModelMixin,
        viewsets.GenericViewSet,
    ):
    queryset = GeoServerGroup.objects.all()
    serializer_class = GeoServerGroupSerializer
    permission_classes = [accounts_permissions.CanAccessOptionMenu,]
    pagination_class = DatatablesPageNumberPagination
    renderer_classes = [DatatablesRenderer,]
    
    # For searching at the backend
    filter_backends = [rest_filters.SearchFilter,]
    search_fields = ["id", "name", "geoserver_roles__name", "geoservergroupuser__user__email"]

    def get_queryset(self):
        return super().get_queryset()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # Role
    @action(detail=True, methods=['get'])
    def roles_related(self, request, pk=None):
        group = shortcuts.get_object_or_404(GeoServerGroup, pk=pk)
        roles = group.geoserver_roles.all()
        serializer = GeoServerRoleSerializer(roles, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def roles_available(self, request, pk=None):
        group = self.get_object()
        roles = GeoServerRole.objects.all().values('id', 'name')
        serializer = GeoServerRoleSerializer(roles, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_role(self, request, pk=None):
        group = self.get_object()
        role_id = request.data.get('role_id')
        if role_id:
            try:
                role = GeoServerRole.objects.get(id=role_id)
                if role not in group.geoserver_roles.all():
                    group.geoserver_roles.add(role)
                    return Response({'success': True})
                else:
                    return Response({'success': False, 'error': 'Role already exists in the group'})
            except GeoServerGroup.DoesNotExist:
                return Response({'success': False, 'error': 'Group not found'}, status=404)
            except GeoServerRole.DoesNotExist:
                return Response({'success': False, 'error': 'Role not found'}, status=404)
            except Exception as e:
                return Response({'success': False, 'error': str(e)}, status=500)

    @action(detail=True, methods=['post'])
    def remove_role(self, request, pk=None):
        group = self.get_object()
        role_id = request.data.get('role_id')
        if role_id:
            try:
                role = GeoServerRole.objects.get(id=role_id)
                if role in group.geoserver_roles.all():
                    group.geoserver_roles.remove(role)
                    return Response({'success': True})
                else:
                    return Response({'success': False, 'error': 'Role is not associated with this group'})
            except Exception as e:
                return Response({'success': False, 'error': str(e)}, status=500)
        else:
            return Response({'error': 'role_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # User
    @action(detail=True, methods=['get'])
    def users_related(self, request, pk=None):
        """
        Retrieves a server-side paginated list of users for the specified group,
        formatted for use with DataTables.js.
        """
        # Step 1: Get the group instance.
        group = self.get_object()

        # Step 2: Build the base queryset.
        # This single query avoids the N+1 problem by querying the UserModel directly
        # through the reverse relationship from the intermediate table.
        queryset = UserModel.objects.filter(
            geoservergroupuser__geoserver_group=group
        ).order_by('id')  # Consistent ordering is required for pagination.

        # Step 3: Let the ViewSet's configured pagination handle the rest.
        # The `pagination_class` defined at the top of the ViewSet will be used.
        page = self.paginate_queryset(queryset)
        
        # self.paginate_queryset returns a page of objects if pagination is active.
        if page is not None:
            # Serialize only the data for the current page.
            serializer = UserSerializer(page, many=True)
            # self.get_paginated_response will use the ViewSet's configured paginator
            # and renderer to return a response in the format DataTables expects.
            return self.get_paginated_response(serializer.data)

        # This part is a fallback in case pagination is somehow disabled,
        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def remove_user(self, request, pk=None):
        group = self.get_object()
        user_id = request.data.get('user_id')
        if user_id:
            try:
                user = UserModel.objects.get(id=user_id)
                relation = GeoServerGroupUser.objects.filter(
                    geoserver_group=group,
                    user=user
                ).first()
                if relation:
                    relation.delete()
                    return Response({'success': True})
                else:
                    return Response({'success': False, 'error': 'User is not associated with this group'})
            except Exception as e:
                return Response({'success': False, 'error': str(e)}, status=500)
        else:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def users_available(self, request, pk=None):
        try:
            geoserver_group = shortcuts.get_object_or_404(GeoServerGroup, pk=pk)
            
            existing_user_ids = GeoServerGroupUser.objects.filter(
                geoserver_group=geoserver_group
            ).values_list('user_id', flat=True)

            search_query = request.query_params.get('search', '')
            page = int(request.query_params.get('page', 1))
            page_size = 20 

            available_users = UserModel.objects.exclude(id__in=existing_user_ids)

            if search_query:
                available_users = available_users.filter(
                    Q(username__icontains=search_query) |
                    Q(email__icontains=search_query)
                )

            # pagination
            # self.renderer_classes = [JSONRenderer,]
            paginator = Paginator(available_users, page_size)
            current_page = paginator.page(page)

            results = [
                {
                    "id": str(user.id),
                    "text": f"{user.username} ({user.email})"
                }
                for user in current_page
            ]

            return Response(results)

        except GeoServerGroup.DoesNotExist:
            return Response(
                {"error": "GeoServer Group not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['POST'])
    def add_user(self, request, pk=None):
        try:
            with transaction.atomic():
                geoserver_group = shortcuts.get_object_or_404(GeoServerGroup, pk=pk)
                user_id = request.data.get('user_id')

                if not user_id:
                    return Response({"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST)

                user = shortcuts.get_object_or_404(UserModel, pk=user_id)

                # Check if the user is already in the group
                if GeoServerGroupUser.objects.filter(geoserver_group=geoserver_group, user=user).exists():
                    return Response({"error": "User is already in the group"}, status=status.HTTP_400_BAD_REQUEST)

                # Add user to the group
                group_user = GeoServerGroupUser(geoserver_group=geoserver_group, user=user)
                group_user.full_clean()  # Validate the model
                group_user.save()

                return Response({"message": f"User {user.username} added to group {geoserver_group.name} successfully"}, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['POST'])
    def create_group(self, request):
        try:
            with transaction.atomic():
                name = request.data.get('name')
                if not name:
                    return Response({"error": "Group name is required"}, status=status.HTTP_400_BAD_REQUEST)

                # Check if a group with this name already exists
                if GeoServerGroup.objects.filter(name=name).exists():
                    return Response({"error": "A group with this name already exists"}, status=status.HTTP_400_BAD_REQUEST)

                # Create the new group
                new_group = GeoServerGroup(name=name)
                new_group.full_clean()  # Validate the model
                new_group.save()

                serializer = self.get_serializer(new_group)
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['DELETE'])
    def delete_group(self, request, pk=None):
        try:
            with transaction.atomic():
                group = shortcuts.get_object_or_404(GeoServerGroup, pk=pk)
                group_name = group.name
                
                # Check if the group has any associated users or resources
                if group.users or group.geoserver_roles.all():
                    return Response({"error": "Cannot delete group. It has associated users or roles."}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    group.delete()
                    return Response({"message": f"Group '{group_name}' has been successfully deleted."}, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({"error": f"An error occurred while deleting the group: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['PATCH'])
    def update_group(self, request, pk=None):
        try:
            with transaction.atomic():
                group = shortcuts.get_object_or_404(GeoServerGroup, pk=pk)
                group_name_old = group.name
                
                new_name = request.data.get('name', '')
                new_active = request.data.get('active', '')

                if not new_name:
                    return Response({"error": f"Name cannot be blank."}, status=status.HTTP_400_BAD_REQUEST)
                if new_active == '':
                    return Response({"error": f"Active status cannot be blank."}, status=status.HTTP_400_BAD_REQUEST)

                serializer = GeoServerGroupSerializer(group, data=request.data)
                serializer.is_valid(raise_exception=True)
                group = serializer.save()
                
                return Response({
                    "message": f"Group '{group_name_old}' has been successfully updated.",
                    "group": {
                        "name": group.name,
                        "active": group.active
                    }
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({"error": f"An error occurred while updating the group: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GeoServerLayerGroupViewSet(
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing GeoServer Layer Groups."""

    queryset = GeoServerLayerGroup.objects.select_related(
        "workspace", "geoserver_pool"
    ).prefetch_related("entries__publish_channel__workspace")
    serializer_class = GeoServerLayerGroupSerializer
    permission_classes = [accounts_permissions.CanAccessOptionMenu]
    pagination_class = DatatablesPageNumberPagination
    renderer_classes = [DatatablesRenderer, JSONRenderer]
    filter_backends = [rest_filters.SearchFilter]
    search_fields = ["name", "title", "workspace__name", "geoserver_pool__name"]

    def destroy(self, request, *args, **kwargs):
        """Delete layer group from GeoServer before removing from the database."""
        layer_group = self.get_object()
        success, exc = geoserver_layergroup_publisher.delete_from_geoserver(layer_group)
        if not success:
            return Response(
                {"error": f"Failed to remove layer group from GeoServer: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        layer_group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Publish the layer group to GeoServer."""
        layer_group = self.get_object()
        success, exc = geoserver_layergroup_publisher.publish(layer_group)
        if not success:
            return Response(
                {"error": f"Failed to publish layer group: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        # Refresh from DB so published_name is current in the response.
        layer_group.refresh_from_db()
        serializer = self.get_serializer(layer_group)
        return Response(serializer.data)


class GeoServerLayerGroupEntryViewSet(
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing individual GeoServerLayerGroupEntry records.

    Used by the frontend to create, update (order), and delete member entries
    without going through the parent group endpoint.
    """

    from govapp.apps.publisher.models.geoserver_layer_groups import GeoServerLayerGroupEntry
    from govapp.apps.publisher.serializers.geoserver_layer_group import GeoServerLayerGroupEntrySerializer

    queryset = GeoServerLayerGroupEntry.objects.all()
    serializer_class = GeoServerLayerGroupEntrySerializer
    permission_classes = [accounts_permissions.CanAccessOptionMenu]


class GeoServerLayerHealthcheckViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.publish_channels.GeoServerLayerHealthcheck.objects.all()
    serializer_class = serializers.publish_channels.GeoServerLayerHealthcheckSerializer
    pagination_class = DatatablesPageNumberPagination
    renderer_classes = [DatatablesRenderer,]  # DatatablesRenderer is required to make pagination work correctly.
    filter_backends = [DatatablesFilterBackend,]
