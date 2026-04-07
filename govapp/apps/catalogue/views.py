"""Kaartdijin Boodja Catalogue Django Application Views."""


# Third-Party
import logging
from django import conf
from django import shortcuts
from django.contrib import auth
from django.db import connection
from django.db import transaction
from django.http import HttpResponse, JsonResponse, FileResponse
from django.core.paginator import Paginator
from drf_spectacular import utils as drf_utils
from rest_framework import decorators
from rest_framework import request
from rest_framework import response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
# from rest_framework_datatables.pagination import DatatablesPageNumberPagination
from rest_framework.response import Response
from datetime import timedelta
from django.core.cache import cache
from owslib.wms import WebMapService
from owslib.wfs import WebFeatureService
import psycopg2
import json
import os
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist

# Local
from govapp import settings
from govapp.apps.publisher.models.publish_channels import GeoServerPublishChannel
from govapp.common import mixins
from govapp.apps.accounts import permissions as accounts_permissions
from govapp.apps.catalogue import filters
from govapp.apps.catalogue import models
from govapp.apps.publisher import models as publish_models
from govapp.apps.catalogue import permissions
from govapp.apps.catalogue import serializers
from govapp.apps.catalogue import utils as catalogue_utils
from govapp.apps.catalogue.postgres_scanner import Scanner
from govapp.apps.catalogue.utils import validate_request
from govapp.apps.catalogue.models import layer_submissions as catalogue_layer_submissions_models
from govapp.apps.logs import mixins as logs_mixins
from govapp.apps.logs import utils as logs_utils


# Typing
from typing import Callable, cast
from typing import Any


# Shortcuts
UserModel = auth.get_user_model()

logger = logging.getLogger(__name__)


@drf_utils.extend_schema(tags=["Catalogue - Catalogue Entries"])
class CatalogueEntryViewSet(
    mixins.ChoicesMixin,
    mixins.HistoryMixin,
    logs_mixins.ActionsLogMixin,
    logs_mixins.CommunicationsLogMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Catalogue Entry View Set."""
    queryset = models.catalogue_entries.CatalogueEntry.objects.all()
    serializer_class = serializers.catalogue_entries.CatalogueEntrySerializer
    filterset_class = filters.CatalogueEntryFilter
    search_fields = ["name", "description", "assigned_to__username", "assigned_to__email", "custodian__name"]    
    permission_classes = [permissions.IsCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        logger.info(f'Updating CatalogueEntry with the data: [{request.data}]...')
        ret = super().update(request, *args, **kwargs)
        
        catalogue_entry = self.get_object()
        msg = f"Catalogue entry: [{catalogue_entry}] has been updated with the data: [{request.data}]."
        logs_utils.add_to_actions_log(
            user=request.user,
            model=catalogue_entry,
            action=msg
        )
        logger.info(msg)

        return ret

    @decorators.action(detail=False, methods=["POST"], permission_classes=[accounts_permissions.IsInCatalogueAdminGroup])
    def delete_file(self, request: request.Request):
        filenameToDelete = request.POST.get('newFileName', '')
        if filenameToDelete:
            pathToFile = os.path.join(settings.PENDING_IMPORT_PATH,  filenameToDelete)
            if os.path.exists(pathToFile):
                os.remove(pathToFile)
                logger.info(f"File: [{pathToFile}] deleted successfully.")
                return JsonResponse({'message': 'File deleted successfully.'})
            else:
                logger.info(f"File: [{pathToFile}] doesn't exist.")
                return JsonResponse({'message': 'File does not exist.'})
        else:
            return JsonResponse({'message': 'No file specified.'})

    @decorators.action(detail=False, methods=["POST"], permission_classes=[accounts_permissions.IsInCatalogueAdminGroup])
    def upload_file(self, request: request.Request):
        if request.FILES:
            # uploaded_files = []  # Multiple files might be uploaded
            allowed_extensions = settings.ALLOWED_EXTENSIONS_TO_UPLOAD
            uploaded_file = request.FILES.getlist('file')[0]
            newFileName = request.POST.get('newFileName', '')

            logger.info(f'File: [{uploaded_file.name}] is being uploaded...')

            # Check file extensions
            _, file_extension = os.path.splitext(uploaded_file.name)
            if file_extension.lower() not in allowed_extensions:
                return JsonResponse({'error': 'Invalid file type. Only .zip and .7z files are allowed.'}, status=400)

            # Save files
            save_path = os.path.join(settings.PENDING_IMPORT_PATH,  newFileName)
            with open(save_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            logger.info(f"File: [{uploaded_file.name}] has been successfully saved at [{save_path}].")
            return JsonResponse({'message': 'File(s) uploaded successfully.'})
        else:
            logger.info(f"No file(s) were uploaded.")
            return JsonResponse({'error': 'No file(s) were uploaded.'}, status=400)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def lock(self, request: request.Request, pk: str) -> response.Response:
        """Locks the Catalogue Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Catalogue Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        try:
            # Retrieve Catalogue Entry
            # Help `mypy` by casting the resulting object to a Catalogue Entry
            # catalogue_entry = self.get_object()
            catalogue_entry = shortcuts.get_object_or_404(models.catalogue_entries.CatalogueEntry, id=pk)
            # catalogue_entry = cast(models.catalogue_entries.CatalogueEntry, catalogue_entry)

            # Lock
            success, message = catalogue_entry.lock()

            # Check Success
            if success:
                # Add Action Log Entry
                logs_utils.add_to_actions_log(
                    user=request.user,
                    model=catalogue_entry,
                    action=f"Catalogue entry: [{catalogue_entry}] has been locked."
                )

                # Return Response
                return response.Response(status=status.HTTP_204_NO_CONTENT)
            else:
                # Return Response
                if not message:
                    message = "Error locking catalogue entry"
                return response.Response(message, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ObjectDoesNotExist as e:
            logger.error(f"Catalogue entry does not exist: {str(e)}")
            return response.Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
            return response.Response({"error": "Error locking catalogue entry"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def unlock(self, request: request.Request, pk: str) -> response.Response:
        """Unlocks the Catalogue Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Catalogue Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Catalogue Entry
        # Help `mypy` by casting the resulting object to a Catalogue Entry
        # catalogue_entry = self.get_object()
        # catalogue_entry = cast(models.catalogue_entries.CatalogueEntry, catalogue_entry)
        catalogue_entry = shortcuts.get_object_or_404(models.catalogue_entries.CatalogueEntry, id=pk)

        # Unlock
        success = catalogue_entry.unlock()

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=catalogue_entry,
                action=f"Catalogue entry: [{catalogue_entry}] has been unlocked."
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def decline(self, request: request.Request, pk: str) -> response.Response:
        """Declines the Catalogue Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Catalogue Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Catalogue Entry
        # Help `mypy` by casting the resulting object to a Catalogue Entry
        catalogue_entry = self.get_object()
        catalogue_entry = cast(models.catalogue_entries.CatalogueEntry, catalogue_entry)

        # Decline
        success = catalogue_entry.decline()

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=catalogue_entry,
                action=f"Catalogue entry: [{catalogue_entry}] has been declined."
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"], url_path=r"assign/(?P<user_pk>\d+)")
    def assign(self, request: request.Request, pk: str, user_pk: str) -> response.Response:
        """Assigns the Catalogue Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Catalogue Entry.
            user_pk (str): Primary key of the User to assign to.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Catalogue Entry
        # Help `mypy` by casting the resulting object to a Catalogue Entry
        catalogue_entry = self.get_object()
        catalogue_entry = cast(models.catalogue_entries.CatalogueEntry, catalogue_entry)

        # Retrieve User
        user = shortcuts.get_object_or_404(UserModel, id=user_pk)

        # Assign!
        success = catalogue_entry.assign(user)

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=catalogue_entry,
                action=f"Catalogue entry: [{catalogue_entry}] has been assigned to {user} (id: {user.pk})"
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def unassign(self, request: request.Request, pk: str) -> response.Response:
        """Unassigns the Catalogue Entry.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Catalogue Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Catalogue Entry
        # Help `mypy` by casting the resulting object to a Catalogue Entry
        catalogue_entry = self.get_object()
        catalogue_entry = cast(models.catalogue_entries.CatalogueEntry, catalogue_entry)

        # Unassign!
        success = catalogue_entry.unassign()

        # Check Success
        if success:
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=catalogue_entry,
                action=f"Catalogue entry: [{catalogue_entry}] has been unassigned."
            )

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    @decorators.action(detail=False, methods=["GET"], permission_classes=[accounts_permissions.IsAuthenticated],
                       url_path=r'(?P<name>\w+)/layer')
    def layer_by_name(self, request: request.Request, name: str):
        """ Api to provide geojson file

        Args:
            request (request.Request): request object passed by Django framework
            name (str): uri parameter represents name of layer submission(catalogue name)

        Returns:
            response.Response: HTTP response with geojson data file
        """
        entry = self.queryset.filter(name=name)
        if entry.exists():
            return self.layer_by_id(request, entry.first().id)
        else:
            return response.Response({"error": 'Invalid query param "name:{name}".'}, 
                                     status=status.HTTP_400_BAD_REQUEST)
        
    @decorators.action(detail=False, methods=["GET"], permission_classes=[accounts_permissions.IsAuthenticated],
                       url_path=r'(?P<id>\d+)/layer')
    def layer_by_id(self, request: request.Request, id: int):
        """ Api to provide geojson file

        Args:
            request (request.Request): request object passed by Django framework
            pk (int): uri parameter represents id of layer submission(catalogue id)

        Returns:
            response.Response: HTTP response with geojson data file
        """
        layer_submission = catalogue_layer_submissions_models.LayerSubmission.objects.filter(catalogue_entry=id, is_active=True).first()

        if not layer_submission.geojson:
            return response.Response(
                {"error": 'The geojson file path cannot be found. The GeoJson file may not has been generated from the TIFF file.'},
                status=status.HTTP_404_NOT_FOUND)
        
        if not os.path.exists(layer_submission.geojson):
            return response.Response(
                {"error": f'The geojson file does not exist at the specified path: [{layer_submission.geojson}].'},
                status=status.HTTP_404_NOT_FOUND)
            
        try:
            resp = FileResponse(open(layer_submission.geojson, 'rb'), 
                                content_type='application/json', 
                                status=status.HTTP_200_OK)
            resp['Content-Disposition'] = 'attachment; filename=' + layer_submission.catalogue_entry.name + '.geojson'
            return resp
        except Exception as e:
            return response.Response({"error": f'An exception occurred while opening the target file: [{ layer_submission.geojson }]. Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @drf_utils.extend_schema(parameters=[drf_utils.OpenApiParameter("days_ago", type=int, required=True)])
    @decorators.action(detail=False, methods=['GET'])
    def recent(self, request: request.Request):
        """ Api to provide sumary of recent catalogue entries from n hours ago

        Args:
            request (request.Request): request object passed by Django framework - must include integer value of days_ago
            pk (str): uri parameter represents id of layer submission(catalogue id)

        Returns:
            response.Response: HTTP response with a list of summary of recent catalogue entries
        """
        
        days_ago = self.request.query_params.get("days_ago")
        
        # validate days_ago
        if days_ago is None or len(days_ago.strip()) == 0:
            return response.Response({"error": 'Field days_ago is required.'}, status=status.HTTP_400_BAD_REQUEST)
        elif not days_ago.isdigit() or int(days_ago) <= 0:
            return response.Response({"error": 'Field house_ago must be a positive integer.'}, status=status.HTTP_400_BAD_REQUEST)

        # select query using inner join and filter
        start_date = self.get_db_now() - timedelta(days=int(days_ago))
        filtered = models.layer_submissions.LayerSubmission.objects.select_related('catalogue_entry').filter(submitted_at__gte=start_date, is_active=True)
        selected = filtered.values('catalogue_entry__id', 'catalogue_entry__name', 'catalogue_entry__created_at', 'catalogue_entry__updated_at', 'id', 'submitted_at')
        
        # build a response data
        response_data = [{
                'id': entry['catalogue_entry__id'],
                'name': entry['catalogue_entry__name'],
                'created_at': entry['catalogue_entry__created_at'],
                'updated_at': entry['submitted_at'],
                'active_layer': entry['id']
            } for entry in list(selected)]
        return response.Response(response_data, content_type='application/json', status=status.HTTP_200_OK)
    
    def get_db_now(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT NOW()")
            result = cursor.fetchone()
            current_time = result[0]
        return current_time
    

@drf_utils.extend_schema(tags=["Catalogue - Custodians"])
class CustodianViewSet(mixins.ChoicesMixin, viewsets.ReadOnlyModelViewSet):
    """Custodian View Set."""
    queryset = models.custodians.Custodian.objects.all()
    serializer_class = serializers.custodians.CustodianSerializer
    filterset_class = filters.CustodianFilter
    search_fields = ["name", "contact_name", "contact_email", "contact_phone"]


@drf_utils.extend_schema(tags=["Catalogue - Layer Attributes"])
class LayerAttributeViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Layer Attribute View Set."""
    queryset = models.layer_attributes.LayerAttribute.objects.all()
    serializer_class = serializers.layer_attributes.LayerAttributeSerializer
    serializer_classes = {"create": serializers.layer_attributes.LayerAttributeCreateSerializer}
    filterset_class = filters.LayerAttributeFilter
    search_fields = ["name", "type", "catalogue_entry__name"]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]

    # to pass the pk to serializer
    def get_serializer_context(self):
        context = super().get_serializer_context()
        if context['request'].method == 'PUT':
            context['pk'] = self.kwargs['pk']
        return context

    def perform_create(self, serializer):
        layer_attribute = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model= layer_attribute.catalogue_entry,
            action=f"LayerAttribute: [{layer_attribute}] has been created with the data: [{serializer.data}]."
        )
        logger.info(f"LayerAttribute: [{layer_attribute}] has been created with the data: [{serializer.data}] from this CatalogueEntry: [{layer_attribute.catalogue_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        layer_attribute = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=layer_attribute.catalogue_entry,
            action=f"LayerAttribute: [{layer_attribute}] has been updated with the data: [{serializer.data}]."
        )
        logger.info(f"LayerAttribute: [{layer_attribute}] has been updated with the data: [{serializer.data}] from the CatalogueEntry: [{layer_attribute.catalogue_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        catalogue_entry = instance.catalogue_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=catalogue_entry,
            action=f"LayerAttribute: [{instance}] has been deleted."
        )
        logger.info(f"LayerAttribute: [{instance}] has been deleted from the CatalogueEntry: [{catalogue_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)


@drf_utils.extend_schema(tags=["Catalogue - Layer Attribute Types"])
class LayerAttributeTypeViewSet(
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet,
):      
    """Layer Attribute Type View Set."""
    queryset = models.layer_attribute_types.LayerAttributeType.objects.all()
    serializer_class = serializers.layer_attribute_types.LayerAttributeTypeSerializer
    filter_backends = []
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]
    pagination_class = None

    
@drf_utils.extend_schema(tags=["Catalogue - Layer Metadata"])
class LayerMetadataViewSet(
    mixins.ChoicesMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Layer Metadata View Set."""
    queryset = models.layer_metadata.LayerMetadata.objects.all()
    serializer_class = serializers.layer_metadata.LayerMetadataSerializer
    filterset_class = filters.LayerMetadataFilter
    search_fields = ["catalogue_entry__name"]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]


@drf_utils.extend_schema(tags=["Catalogue - Layer Submissions2"])
class LayerSubmissionDatatableViewSet(
    mixins.ChoicesMixin,
    logs_mixins.ActionsLogMixin,
    logs_mixins.CommunicationsLogMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Layer Submission View Set."""
    queryset = models.layer_submissions.LayerSubmission.objects.all()
    serializer_class = serializers.layer_submissions.LayerSubmissionSerializer
    filterset_class = filters.LayerSubmissionFilter
    search_fields = ["id",]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]

    def list(self, request, *args, **kwargs):
        # Retrieve all the layer submissions
        recordsTotal = self.get_queryset()

        catalogue_entry_id = request.GET.get('catalogue_entry_id', False)
        if catalogue_entry_id:
            # Filter by the catalogue entry
            recordsTotal = recordsTotal.filter(catalogue_entry_id=catalogue_entry_id)

        # Store the total number to return to the datatable in the frontend
        recordsTotalCount = recordsTotal.count()

        # Filter the queryset
        queryset = self.filter_queryset(recordsTotal)

        # Sorting
        ordering = request.GET.get('order[0][column]')
        if ordering:
            column_index = int(ordering)
            column_name = request.GET.get('columns[{}][data]'.format(column_index))
            order_dir = request.GET.get('order[0][dir]')
            if column_name and order_dir:
                if order_dir == 'asc':
                    queryset = queryset.order_by(column_name)
                else:
                    queryset = queryset.order_by(f'-{column_name}')
        
        # Pagination
        page_size = int(request.GET.get('length', 10))

        # Create a Paginator object with the queryset and page size
        paginator = Paginator(queryset, page_size)

        # Calculate the current page number based on the 'start' query parameter
        page_number = int(request.GET.get('start', 0)) // page_size + 1

        # Get the current page from the Paginator
        page = paginator.get_page(page_number)

        # Serialize the current page data
        serializer = self.get_serializer(page, many=True)

        # Prepare the response data for DataTables
        response_data = {
            'draw': int(request.GET.get('draw', 1)),
            'recordsTotal': recordsTotalCount,
            'recordsFiltered': queryset.count(),
            'data': serializer.data
        }

        return Response(response_data)


@drf_utils.extend_schema(tags=["Catalogue - Layer Submissions"])
class LayerSubmissionViewSet(
    mixins.ChoicesMixin,
    logs_mixins.ActionsLogMixin,
    logs_mixins.CommunicationsLogMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Layer Submission View Set."""
    queryset = models.layer_submissions.LayerSubmission.objects.all()
    serializer_class = serializers.layer_submissions.LayerSubmissionSerializer
    filterset_class = filters.LayerSubmissionFilter
    search_fields = ["description", "catalogue_entry__name"]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]

    @decorators.action(detail=True, methods=["GET"], url_path="file", permission_classes=[accounts_permissions.IsAuthenticated])
    def download_file(self, request: request.Request, pk: str):
        layer_submission = shortcuts.get_object_or_404(models.layer_submissions.LayerSubmission, id=pk)
        user_access_permission = layer_submission.get_user_access_permission(request.user)
        if layer_submission.is_restricted and user_access_permission not in ['read', 'read_write',]:
            return response.Response({'error_msg':f'User does not have permissions to access the file.'}, status=status.HTTP_403_FORBIDDEN)

        file_path = self.queryset.get(id=pk).file

        if file_path == None or os.path.exists(file_path) == False:
            return response.Response({"message":"The target file does not exist."}, 
                                     content_type='application/json', 
                                     status=status.HTTP_404_NOT_FOUND)
            
        with open(file_path, 'rb') as fh:
            res = HttpResponse(fh.read(), 
                                content_type='application/octet-stream', 
                                status=status.HTTP_200_OK)
            res['Content-Disposition'] = 'attachment; filename=' + os.path.basename(file_path)
            res['Filename'] = os.path.basename(file_path)
            return res
        

@drf_utils.extend_schema(tags=["Catalogue - Layer Subscriptions"])
class LayerSubscriptionViewSet(
    mixins.ChoicesMixin, 
    mixins.MultipleSerializersMixin,
    logs_mixins.ActionsLogMixin,
    logs_mixins.CommunicationsLogMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet): 
                            #    viewsets.ReadOnlyModelViewSet):
    """Layer Subscription View Set."""
    queryset = models.layer_subscriptions.LayerSubscription.objects.all()
    serializer_class = serializers.layer_subscriptions.LayerSubscriptionSerializer
    serializer_classes = {"create":serializers.layer_subscriptions.LayerSubscriptionCreateSerializer,
                          "update":serializers.layer_subscriptions.LayerSubscriptionUpdateSerializer}
    filterset_class = filters.LayerSubscriptionFilter
    search_fields = ["catalogue_entry__name"]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]

    def create(self, request):
        # Validation check
        data = validate_request(self.serializer_classes['create'], request.data)
        
        # Convert data types
        for key in data:
            if key in ['type', 'connection_timeout', 'max_connections', 'read_timeout'] and data.get(key) is not None:
                data[key] = int(data.get(key))
                
        # Check duplicated catalogue entry name
        if models.catalogue_entries.CatalogueEntry.objects.filter(name=data['name']).exists():
            return response.Response({'error_msg':f"catalogue entry name '{data['name']}' has been already taken."}, 
                                      content_type='application/json', status=status.HTTP_400_BAD_REQUEST)     
        
        # Check type
        type = None
        try:
            type = catalogue_utils.find_enum_by_value(models.layer_subscriptions.LayerSubscriptionType, data.get('type'))
            # type = {type.value:type for type in models.layer_subscriptions.LayerSubscriptionType}.get()
        except ValueError as exc:
            return response.Response({'error_msg':f"type '{data.get('type')}' is invalid."}, 
                                    content_type='application/json', status=status.HTTP_400_BAD_REQUEST) 
        
        # Create layer subscription
        models.layer_subscriptions.LayerSubscription.objects.create(
            type=type,
            name=data.get('name'),
            description=data.get('description'),
            workspace=data.get('workspace'),
            enabled=data.get('enabled'),
            url=data.get('url'),
            host=data.get('host'),
            port=data.get('port'),
            database=data.get('database'),
            username=data.get('username'),
            userpassword=data.get('userpassword'),
            connection_timeout=data.get('connection_timeout'),
            max_connections=data.get('max_connections'),
            min_connections=data.get('min_connections'),
            read_timeout=data.get('read_timeout'),
            schema=data.get('schema'),
            fetch_size=data.get('fetch_size'),
            ssl_mode=data.get('ssl_mode')
        )
        
        return response.Response({'msg':"success"}, content_type='application/json', status=status.HTTP_200_OK)
    
    def update(self, request: request.Request, pk: str):
        
        # Retrieve object from DB
        subscription = self.get_object()
        subscription_obj = cast(models.layer_subscriptions.LayerSubscription, subscription)
        
        # Validation check
        data = request.data
        data['type'] = subscription_obj.type
        data = validate_request(self.serializer_classes['update'], data)
        
        if subscription_obj.is_locked():
             return response.Response({'error_msg':f'This  subscription "{pk}" is locked.'}, 
                                      content_type='application/json', status=status.HTTP_404_NOT_FOUND)
        
        # Convert string numbers to integer
        for key in data:
            if key in ['workspace', 'connection_timeout', 'max_connections', 'read_timeout'] and data.get(key) is not None:
                data[key] = int(data.get(key))
        
        ### Update subscription
        # Check workspace
        workspace = None
        if 'workspace' in data:
            workspace = publish_models.workspaces.Workspace.objects.filter(id=data.get('workspace'))
            if not workspace.exists():
                return response.Response({'error_msg':f"workspace '{data.get('workspace')}' does not exist."}, 
                                        content_type='application/json', status=status.HTTP_400_BAD_REQUEST)
            data['workspace'] = workspace.first()
        
        for key in data:
            setattr(subscription_obj, key, data[key])
        
        subscription_obj.save()

        safe_data = {k: ('***' if k == 'userpassword' else v) for k, v in data.items()}
        msg=f'Layer subscription: [{subscription_obj}] has been updated with the data: [{safe_data}].'
        logs_utils.add_to_actions_log(
            user=request.user,
            model=subscription_obj,
            action=msg
        )
        logger.info(msg)
        
        return response.Response({'msg':"success"}, content_type='application/json', status=status.HTTP_200_OK)
    
    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def lock(self, request: request.Request, pk: str) -> response.Response:
        """Locks the Layer Subscription.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)

        # Lock
        success = subscription.lock()

        # Check Success
        if success:
            msg=f"Layer Subscription: [{subscription}] has been locked."
            # Add Action Log Entry
            logs_utils.add_to_actions_log(
                user=request.user,
                model=subscription,
                action=msg
            )
            logger.info(msg)

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def unlock(self, request: request.Request, pk: str) -> response.Response:
        """Unlocks the Layer Subscription.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)

        # Unlock
        success = subscription.unlock()

        # Check Success
        if success:
            # Add Action Log Entry
            msg=f"Layer Subscription: [{subscription}] has been unlocked."
            logs_utils.add_to_actions_log(
                user=request.user,
                model=subscription,
                action=msg,
            )
            logger.info(msg)

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"], url_path=r"assign/(?P<user_pk>\d+)")
    def assign(self, request: request.Request, pk: str, user_pk: str) -> response.Response:
        """Assigns the Layer Subscription.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.
            user_pk (str): Primary key of the User to assign to.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)

        # Retrieve User
        user = shortcuts.get_object_or_404(UserModel, id=user_pk)

        # Assign!
        success = subscription.assign(user)

        # Check Success
        if success:
            # Add Action Log Entry
            msg=f"Layer Subscription has been assigned to the user: [{user} (id: {user.pk})]."
            logs_utils.add_to_actions_log(
                user=request.user,
                model=subscription,
                action=msg
            )
            logger.info(msg)

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)

    @drf_utils.extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"])
    def unassign(self, request: request.Request, pk: str) -> response.Response:
        """Unassigns the Layer Subscription.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)

        # Unassign!
        success = subscription.unassign()

        # Check Success
        if success:
            # Add Action Log Entry
            msg="Layer Subscription was unassigned"
            logs_utils.add_to_actions_log(
                user=request.user,
                model=subscription,
                action=msg
            )
            logger.info(msg)

        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryCreateSubscriptionMappingSerializer,
        responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"], url_path="mapping")
    def mapping(self, request: request.Request, pk: str,) -> response.Response:
        """Add mapping to target service.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)
        
        # Set Type
        catalogue_type = models.catalogue_entries.CatalogueEntryType.SUBSCRIPTION_WFS
        if subscription.type == models.layer_subscriptions.LayerSubscriptionType.WFS:
            catalogue_type = models.catalogue_entries.CatalogueEntryType.SUBSCRIPTION_WFS
        elif subscription.type == models.layer_subscriptions.LayerSubscriptionType.WMS:
            catalogue_type = models.catalogue_entries.CatalogueEntryType.SUBSCRIPTION_WMS
        elif subscription.type == models.layer_subscriptions.LayerSubscriptionType.POST_GIS:
            catalogue_type = models.catalogue_entries.CatalogueEntryType.SUBSCRIPTION_POSTGIS

        try:
            data = request.data.copy()
            data['type'] = catalogue_type
            data['layer_subscription'] = subscription.id

            # Create Catalogue Entry
            serializer = serializers.catalogue_entries.CatalogueEntryCreateSubscriptionMappingSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            catalogue_entry = serializer.save()
            logger.info(f'New CatalogueEntry: [{catalogue_entry}] has been created with the data: [{data}].')

            from govapp.gis.readers import base
            layer_symbology, created = models.layer_symbology.LayerSymbology.objects.get_or_create(
                sld=base.DEFAULT_SLD,
                catalogue_entry=catalogue_entry,
            )
            logger.info(f'New LayerSymbology: [{layer_symbology}] has been created for the CatalogueEntry: [{catalogue_entry}].')

            logs_utils.add_to_actions_log(
                user=request.user,
                model=catalogue_entry,
                action=f'Created with the data: [{data}] from the layer subscription: [{subscription}].'
            )
            logs_utils.add_to_actions_log(
                user=request.user,
                model=subscription,
                action=f'New CatalogueEntry: [{catalogue_entry}] has been created.'
            )
            return response.Response(status=status.HTTP_204_NO_CONTENT)
        except ValueError as e:
            logger.info(f'CatalogueEntry with the name: [{data['name']}] already exists.')
            return response.Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryUpdateSubscriptionMappingSerializer,
        responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["PUT"], url_path=r"mapping/(?P<catalogue_id>\d+)")
    def update_mapping(self, request: request.Request, pk: str, catalogue_id: str) -> response.Response:
        """Update mapping to target service.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.
            catalogue_id (str): Primary key of the Catalogue Entry.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)
        
        # Check Catalogue Entry
        if not models.catalogue_entries.CatalogueEntry.objects.filter(id=catalogue_id).exists():
            return response.Response({'error_msg':f'catalogue entry({catalogue_id}) does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.get(id=catalogue_id)
        
        # Validation check
        # data = validate_request(serializers.catalogue_entries.CatalogueEntryUpdateSubscriptionMappingSerializer, request.data)
        serializer = serializers.catalogue_entries.CatalogueEntryUpdateSubscriptionMappingSerializer(catalogue_entry, data=request.data)
        serializer.is_valid(raise_exception=True)
        catalogue_entry = serializer.save()

        logs_utils.add_to_actions_log(
            user=request.user,
            model=catalogue_entry,
            action=f'CatalogueEntry: [{catalogue_entry}] has been updated with the data: [{request.data}] from the layer subscription: [{subscription}].'
        )
        logs_utils.add_to_actions_log(
            user=request.user,
            model=subscription,
            action=f'CatalogueEntry: [{catalogue_entry}] has been updated.'
        )
        logger.info(f'CatalogueEntry: [{catalogue_entry}] has been updated with the data: [{request.data}]')
        
        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryGetSubscriptionMappingSerializer,
        responses={status.HTTP_200_OK: None})
    @mapping.mapping.get
    def get_mapping(self, request: request.Request, pk: str) -> response.Response:
        """Add mapping to target service.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: A dictionary of mapping data.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        layer_subscription = self.get_object()
        layer_subscription = cast(models.layer_subscriptions.LayerSubscription, layer_subscription)
        
        entries = models.catalogue_entries.CatalogueEntry.objects.filter(layer_subscription=layer_subscription)
        mappings = [
            {
                'id': entry.id,
                'mapping_name': entry.mapping_name,
                'name': entry.name,
                'description': entry.description,
                'is_custom_query': entry.is_custom_query
            }
            for entry in entries
        ]

        # Return Response
        logger.debug(f'mappings: {mappings}')
        return response.Response({'results':mappings}, content_type='application/json', status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["GET"], url_path="check_connection")
    def check_connection(self, request: request.Request, pk: str):
        try:
            subscription = self.get_object()
            subscription_obj = cast(models.layer_subscriptions.LayerSubscription, subscription)
            server_obj = subscription_obj.check_connection()
            return response.Response(
                {'results': 'success'},
                content_type='application/json',
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error occurred while checking connection: {str(e)}")
            return response.Response(
                {'results': str(e)},
                content_type='application/json',
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryUpdateSubscriptionMappingSerializer,
        responses={status.HTTP_200_OK: None})
    @decorators.action(detail=True, methods=["GET"], url_path="mapping/source")
    def get_mapping_source(self, request: request.Request, pk: str) -> response.Response:
        """Response mapping source.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: A list of mapping source names
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription_obj = cast(models.layer_subscriptions.LayerSubscription, subscription)

        force_to_query = request.GET.get('force_to_query', '').strip().lower()
        if force_to_query in ['true', 't', '1', 'yes', 'y']:
            force_to_query = True
        elif force_to_query in ['false', 'f', '0', 'no', 'n']:
            force_to_query = False
        else:
            # This is default value
            force_to_query = False

        mapping_names = models.layer_subscriptions.LayerSubscriptionData.retrieve_latest_data(subscription_obj, force_to_query)
        return response.Response(
            {'results':mapping_names},
            content_type='application/json',
            status=status.HTTP_200_OK
        )
        
    @transaction.atomic()
    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryCreateSubscriptionQuerySerializer,
        responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["POST"], url_path="query")
    def query(self, request: request.Request, pk: str,) -> response.Response:
        """Add a custom query.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)
        
        # Validation check
        data = validate_request(serializers.catalogue_entries.CatalogueEntryCreateSubscriptionQuerySerializer, request.data)
        if 'frequency_type' not in request.data:
            raise ValidationError("frequency_type is required")
        frequency_type = request.data['frequency_type']
        if ('frequency_options' not in request.data or
            type(request.data['frequency_options']) != list):
            raise ValidationError("frequency_options is required")
        frequency_options = request.data['frequency_options']
        self._validate_frequency(frequency_type, frequency_options)
            
        # Create Catalogue Entry
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.create(
            name=data['name'],
            description=data['description'] if 'description' in data else None,
            sql_query=data['sql_query'],
            type=models.catalogue_entries.CatalogueEntryType.SUBSCRIPTION_QUERY,
            layer_subscription=subscription
        )
        msg = f'This CatalogueEntry: [{catalogue_entry}] has been created from the subscription: [{subscription}].'
        logger.info(msg)
        logs_utils.add_to_actions_log(
            user=request.user,
            model=catalogue_entry,
            action=msg
        )

        msg = f'New CatalogueEntry: [{catalogue_entry}] has been created from this subscription: [{subscription}].'
        logs_utils.add_to_actions_log(
            user=request.user,
            model=subscription,
            action=msg
        )
        
        # Create Custom Query Frequency
        for option in frequency_options:
            freq_options = self._make_frequency_option(frequency_type, option)
            freq_options['catalogue_entry'] = catalogue_entry
            freq_options['type'] = frequency_type
            models.custom_query_frequency.CustomQueryFrequency.objects.create(**freq_options)
        
        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    def _validate_frequency(self, frequency_type, frequency_options):
        for option in frequency_options:
            if frequency_type == models.custom_query_frequency.FrequencyType.EVERY_MINUTES:
                if 'minutes' not in option:
                    raise ValidationError("minutes is required if FrequencyType is EVERY_MINUTES(1)")
            elif frequency_type == models.custom_query_frequency.FrequencyType.EVERY_HOURS:
                if 'hours' not in option:
                    raise ValidationError("hours is required if FrequencyType is EVERY_HOURS(2)")
                pass
            elif frequency_type == models.custom_query_frequency.FrequencyType.DAILY:
                if 'hour' not in option or 'minute' not in option:
                    raise ValidationError("hour and minute is required if FrequencyType is DAILY(3)")
            elif frequency_type == models.custom_query_frequency.FrequencyType.WEEKLY:
                if 'hour' not in option or 'minute' not in option or 'day' not in option:
                    raise ValidationError("hour, minute, and day is required if FrequencyType is WEEKLY(4)")
            elif frequency_type == models.custom_query_frequency.FrequencyType.MONTHLY:
                if 'hour' not in option or 'minute' not in option or 'date' not in option:
                    raise ValidationError("hour, minute, and date is required if FrequencyType is MONTHLY(4)")
                
    def _make_frequency_option(self, frequency_type, option):
        freq_options = {}
        
        if frequency_type == models.custom_query_frequency.FrequencyType.EVERY_MINUTES:
            freq_options['every_minutes'] = option['minutes']
        elif frequency_type == models.custom_query_frequency.FrequencyType.EVERY_HOURS:
            freq_options['every_hours'] = option['hours']
        elif frequency_type == models.custom_query_frequency.FrequencyType.DAILY:
            freq_options['hour'] = option['hour']
            freq_options['minute'] = option['minute']
        elif frequency_type == models.custom_query_frequency.FrequencyType.WEEKLY:
            freq_options['hour'] = option['hour']
            freq_options['minute'] = option['minute']
            freq_options['day_of_week'] = option['day']
        elif frequency_type == models.custom_query_frequency.FrequencyType.MONTHLY:
            freq_options['hour'] = option['hour']
            freq_options['minute'] = option['minute']
            freq_options['date'] = option['date']
            
        return freq_options
    
    @transaction.atomic()
    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryUpdateSubscriptionQuerySerializer,
        responses={status.HTTP_204_NO_CONTENT: None})
    @decorators.action(detail=True, methods=["PUT"], url_path=r"query/(?P<catalogue_id>\d+)")
    def update_query(self, request: request.Request, pk: str, catalogue_id: str) -> response.Response:
        """Update a custom query.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: Empty response confirming success.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)
        
        catalogue_entry = models.catalogue_entries.CatalogueEntry.objects.get(pk=catalogue_id)
        serializer = serializers.catalogue_entries.CatalogueEntryUpdateSubscriptionQuerySerializer(catalogue_entry, request.data)
        serializer.is_valid(raise_exception=True)
        catalogue_entry = serializer.save()

        msg = f'CatalogueEntry: [{catalogue_entry}] has been updated by the user: [{request.user}] from the subscription: [{subscription}].'
        logger.info(msg)
        logs_utils.add_to_actions_log(
            user=request.user,
            model=catalogue_entry,
            action=f'CatalogueEntry: [{catalogue_entry}] has been updated from the subscription: [{subscription}].'
        )
        logs_utils.add_to_actions_log(
            user=request.user,
            model=subscription,
            action=f'CatalogueEntry: [{catalogue_entry}] has been updated.'
        )
        
        if 'frequency_type' not in request.data:
            raise ValidationError("frequency_type is required")
        frequency_type = request.data['frequency_type']
        if ('frequency_options' not in request.data or
            type(request.data['frequency_options']) != list):
            raise ValidationError("frequency_options is required")
        frequency_options = request.data['frequency_options']
        self._validate_frequency(frequency_type, frequency_options)
        
        # Update Custom Query Frequency
        models.custom_query_frequency.CustomQueryFrequency.objects.filter(catalogue_entry=catalogue_entry).delete()
        for option in frequency_options:
            freq_options = self._make_frequency_option(frequency_type, option)
            freq_options['catalogue_entry'] = catalogue_entry
            freq_options['type'] = frequency_type
            models.custom_query_frequency.CustomQueryFrequency.objects.create(**freq_options)
        
        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryGetSubscriptionQuerySerializer,
        responses={status.HTTP_200_OK: None})
    # @decorators.action(detail=True, methods=["GET"], url_path="query")
    @query.mapping.get
    def get_query(self, request: request.Request, pk: str) -> response.Response:
        """get a custom query.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: A dictionary of mapping data.
        """
        # Retrieve Layer Subscription
        # Help `mypy` by casting the resulting object to a Layer Subscription
        subscription = self.get_object()
        subscription = cast(models.layer_subscriptions.LayerSubscription, subscription)
        
        # Retrieve Catalogue Entry with Layer Submission Id
        catalogue_entries = subscription.catalogue_entries.exclude(
            Q(sql_query__isnull=True)  # When the sql_query is Null, this catalogue_entry is not the object for the custon query.
        ).prefetch_related('custom_query_frequencies').all()
        results = []
        for catalogue_entry in catalogue_entries:
            frequencies = []
            for freq in catalogue_entry.custom_query_frequencies.all():
                frequencies.append({
                    'type':freq.type, 
                    'type_label': freq.get_type_display(),
                    'minutes':freq.every_minutes, 
                    'hours':freq.every_hours,
                    'hour':freq.hour,
                    'minute':freq.minute,
                    'day':freq.day_of_week,
                    'date':freq.date,
                })
            results.append({
                'id': catalogue_entry.id,
                'name': catalogue_entry.name,
                'description' : catalogue_entry.description,
                'sql_query' : catalogue_entry.sql_query,
                'frequencies' : frequencies,
                'force_run_postgres_scanner': catalogue_entry.force_run_postgres_scanner,
            })
            
        # Return Response
        return response.Response({'results':results}, content_type='application/json', status=status.HTTP_200_OK)
    
    @decorators.action(detail=True, methods=["POST"], url_path=r"convert-query/(?P<catalogue_id>\d+)")
    def convert_query(self, request: request.Request, pk: str, catalogue_id: str) -> response.Response:
        try:
            catalogue_entry_obj = shortcuts.get_object_or_404(models.catalogue_entries.CatalogueEntry, id=catalogue_id)
            new_path = Scanner.run_postgres_to_shapefile(catalogue_entry_obj)
            return response.Response({'message': f'[CE{catalogue_entry_obj.id}: {catalogue_entry_obj.name}] has been converted to the shapefile: [{new_path}].'}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return response.Response({"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @drf_utils.extend_schema(
        request=serializers.catalogue_entries.CatalogueEntryGetSubscriptionQuerySerializer,
        responses={status.HTTP_200_OK: None})
    @decorators.action(detail=True, methods=["DELETE"], url_path=r"delete-query/(?P<catalogue_id>\d+)")
    def delete_query(self, request: request.Request, pk: str, catalogue_id: str) -> response.Response:
        """delete a custom query.

        Args:
            request (request.Request): API request.
            pk (str): Primary key of the Layer Subscription.

        Returns:
            response.Response: A dictionary of mapping data.
        """
        # Retrieve Catalogue Entry with Layer Submission Id
        models.catalogue_entries.CatalogueEntry.objects.get(pk=catalogue_id).delete()
        msg = f'CatalogueEntry (id: {catalogue_id}) has been deleted by the user: [{request.user}].'
        logger.info(msg)
        # logs_utils.add_to_actions_log(
        #     user=request.user,
        #     model=catalogue_entry,
        #     action=msg
        # )
            
        # Return Response
        return response.Response(status=status.HTTP_204_NO_CONTENT)
    
@drf_utils.extend_schema(tags=["Catalogue - Layer Symbology"])
class LayerSymbologyViewSet(
    mixins.ChoicesMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Layer Symbology View Set."""
    queryset = models.layer_symbology.LayerSymbology.objects.all()
    serializer_class = serializers.layer_symbology.LayerSymbologySerializer
    filterset_class = filters.LayerSymbologyFilter
    search_fields = ["catalogue_entry__name"]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]


@drf_utils.extend_schema(tags=["Catalogue - Notifications (Email)"])
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
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]
    
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
            model= email_notification.catalogue_entry,
            action=f"EmailNotification: [{email_notification}] has been created with the data: [{serializer.data}]."
        )
        logger.info(f"EmailNotification: [{email_notification}] has been created with the data: [{serializer.data}] from this CatalogueEntry: [{email_notification.catalogue_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        email_notification = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=email_notification.catalogue_entry,
            action=f"EmailNotification: [{email_notification}] has been updated with the data: [{serializer.data}]."
        )
        logger.info(f"EmailNotification: [{email_notification}] has been updated with the data: [{serializer.data}] from the CatalogueEntry: [{email_notification.catalogue_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        catalogue_entry = instance.catalogue_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=catalogue_entry,
            action=f"EmailNotification: [{instance}] has been deleted."
        )
        logger.info(f"EmailNotification: [{instance}] has been deleted from the CatalogueEntry: [{catalogue_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)
    

@drf_utils.extend_schema(tags=["Catalogue - Notifications (Webhook)"])
class WebhookNotificationViewSet(
    mixins.ChoicesMixin,
    mixins.MultipleSerializersMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Webhook Notification View Set."""
    queryset = models.notifications.WebhookNotification.objects.all()
    serializer_class = serializers.notifications.WebhookNotificationSerializer
    serializer_classes = {"create": serializers.notifications.WebhookNotificationCreateSerializer}
    filterset_class = filters.WebhookNotificationFilter
    search_fields = ["name", "url"]
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]


@drf_utils.extend_schema(tags=["Catalogue - Permissions"])
class CatalogueEntryPermissionViewSet(
    mixins.MultipleSerializersMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):      
    """Catalogue Permission View Set."""
    queryset = models.permission.CatalogueEntryPermission.objects.all()
    serializer_class = serializers.permission.CatalogueEntryPermissionSerializer
    serializer_classes = {"create": serializers.permission.CatalogueEntryPermissionCreateSerializer}
    filterset_class = filters.CataloguePermissionFilter
    permission_classes = [permissions.HasCatalogueEntryPermissions | accounts_permissions.IsInAdministratorsGroup]
    pagination_class = None

    def perform_create(self, serializer):
        catalogue_entry_permission = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model= catalogue_entry_permission.catalogue_entry,
            action=f"AccessPermission: [{catalogue_entry_permission}] has been created with the data: [{serializer.data}]."
        )
        logger.info(f"AccessPermission: [{catalogue_entry_permission}] has been created with the data: [{serializer.data}] from this CatalogueEntry: [{catalogue_entry_permission.catalogue_entry}] by the user: [{self.request.user}].")

    def perform_update(self, serializer):
        catalogue_entry_permission = serializer.save()
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=catalogue_entry_permission.catalogue_entry,
            action=f"AccessPermission: [{catalogue_entry_permission}] has been updated with the data: [{serializer.data}]."
        )
        logger.info(f"AccessPermission: [{catalogue_entry_permission}] has been updated with the data: [{serializer.data}] from the CatalogueEntry: [{catalogue_entry_permission.catalogue_entry}] by the user: [{self.request.user}].")

    def perform_destroy(self, instance):
        catalogue_entry = instance.catalogue_entry
        logs_utils.add_to_actions_log(
            user=self.request.user,
            model=catalogue_entry,
            action=f"AccessPermission: [{instance}] has been deleted."
        )
        logger.info(f"AccessPermission: [{instance}] has been deleted from the CatalogueEntry: [{catalogue_entry}] by the user: [{self.request.user}].")
        return super().perform_destroy(instance)
