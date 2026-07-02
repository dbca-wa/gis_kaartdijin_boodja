"""Kaartdijin Boodja Accounts Django Application Views."""

import os

# Third-Party
from django.contrib import auth
from django.contrib.auth import models
from django.http import FileResponse, HttpResponseForbidden
from drf_spectacular import utils
from rest_framework import decorators
from rest_framework import request
from rest_framework import response
from rest_framework import viewsets
from rest_framework import views
from rest_framework import permissions


# Local
from govapp import settings
from govapp.apps.accounts import serializers
from govapp.apps.accounts import filters
from govapp.apps.accounts.utils import get_file_list


# Shortcuts
UserModel = auth.get_user_model()
GroupModel = models.Group


@utils.extend_schema(tags=["Accounts - Users"])
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """User View Set."""
    permission_classes = [permissions.IsAuthenticated]
    queryset = UserModel.objects.all()
    serializer_class = serializers.UserSerializer
    filterset_class = filters.UserFilter

    @utils.extend_schema(request=None, responses=serializers.UserSerializer)
    @decorators.action(detail=False, methods=["GET"])
    def me(self, request: request.Request) -> response.Response:
        """Retrieves the currently logged in user.

        Args:
            request (request.Request): API request.

        Returns:
            response.Response: The currently logged in user if applicable.
        """
        # Retrieve User
        instance = request.user

        # Serialize User
        serializer = self.get_serializer(instance)

        # Return Response
        return response.Response(serializer.data)


@utils.extend_schema(tags=["Accounts - Groups"])
class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    """Group View Set."""
    permission_classes = [permissions.IsAuthenticated]
    queryset = GroupModel.objects.all()
    serializer_class = serializers.GroupSerializer


class FileListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        config_path = os.path.join(settings.BASE_DIR, 'config')

        try:
            file_list, num_of_files = get_file_list(config_path)
            return response.Response({
                'count': num_of_files,
                'results': file_list
            })

        except Exception as e:
            raise RuntimeError(f"Error while retrieving file metadata: {str(e)}")


class FileDownloadView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        file_path = request.query_params.get('filepath', None)
        
        if not file_path:
            return response.Response({'error': 'File path is required as query parameter.'}, status=400)
        
        # Construct full path
        config_path = os.path.join(settings.BASE_DIR, 'config')
        file_full_path = os.path.join(config_path, file_path)

        # Check if the file is within the config directory and is a file
        common_path = os.path.commonpath([file_full_path, config_path,])
        if common_path == config_path and os.path.exists(file_full_path) and os.path.isfile(file_full_path):
            try:
                return FileResponse(open(file_full_path, 'rb'), as_attachment=True, filename=os.path.basename(file_full_path))
            except Exception as e:
                return response.Response({'error': str(e)}, status=500)
        else:
            return HttpResponseForbidden("You do not have permission to access this file.")


class FileDeleteView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        file_path = request.query_params.get('filepath', None)
        
        if not file_path:
            return response.Response({'error': 'File path is required as query parameter.'}, status=400)
        
        # Construct full path
        config_path = os.path.join(settings.BASE_DIR, 'config')
        file_full_path = os.path.join(config_path, file_path)

        # Check if the file is within the config directory and is a file
        common_path = os.path.commonpath([file_full_path, config_path])
        if common_path == config_path and os.path.exists(file_full_path) and os.path.isfile(file_full_path):
            try:
                os.remove(file_full_path)
                return response.Response({'message': 'File deleted successfully.'}, status=200)
            except Exception as e:
                return response.Response({'error': str(e)}, status=500)
        else:
            return HttpResponseForbidden("You do not have permission to access or delete this file.")
