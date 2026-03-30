"""Kaartdijin Boodja Accounts Django Application Permissions."""


# Third-Party
from rest_framework import permissions
from rest_framework import request
from rest_framework import viewsets

# Local
from govapp.apps.accounts import utils

# Typing
from typing import Any


class IsInCatalogueAdminGroup(permissions.BasePermission):
    def has_permission(self, request, view):
        return utils.is_catalogue_admin(request.user)


class IsInAdministratorsGroup(permissions.BasePermission):
    """Permissions for the a user in the Administrators group."""

    def has_permission(  # type: ignore
        self,
        request: request.Request,
        view: viewsets.GenericViewSet,
    ) -> bool:
        """Checks viewset request level permissions.

        Args:
            request (request.Request): Request to check permissions.
            view (viewsets.GenericViewSet): Viewset to check permissions.

        Returns:
            bool: Whether permission is allowed.
        """
        # Return
        return utils.is_administrator(request.user)

    def has_object_permission(  # type: ignore
        self,
        request: request.Request,
        view: viewsets.GenericViewSet,
        obj: Any,
    ) -> bool:
        """Checks object level permissions.

        Args:
            request (request.Request): Request to check permissions.
            view (viewsets.GenericViewSet): Viewset to check permissions.
            obj (Any): Object to check permissions.

        Returns:
            bool: Whether permission is allowed.
        """
        # Return
        return utils.is_administrator(request.user)


class IsAuthenticated(permissions.BasePermission):
    """Permissions whether the user is authenticated."""

    def has_permission(  # type: ignore
        self,
        request: request.Request,
        view: viewsets.GenericViewSet,
    ) -> bool:
        """Checks viewset request level permissions.

        Args:
            request (request.Request): Request to check permissions.
            view (viewsets.GenericViewSet): Viewset to check permissions.

        Returns:
            bool: Whether permission is allowed.
        """
        # Return
        return request.user.is_authenticated


class BaseStaffSuperuserPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated:
            if request.user.is_staff or request.user.is_superuser:
                return True
        return False

class CanAccessOptionMenu(BaseStaffSuperuserPermission):
    pass

class CanAccessCDDP(BaseStaffSuperuserPermission):
    def has_permission(self, request, view):
        if utils.is_api_user(request.user):  # This conditional is specific to the CDDP.  We allow the windows script to access the CDDP
            return True
        return super().has_permission(request, view)


class IsApiUser(permissions.BasePermission):
    """Allow access only to authenticated users in the 'API User' group."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and utils.is_api_user(request.user)