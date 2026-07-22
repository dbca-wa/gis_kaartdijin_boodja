"""Kaartdijin Boodja Catalogue Django Application Permissions."""


# Third-Party
from rest_framework import permissions
from rest_framework import request
from rest_framework import viewsets

# Local
from govapp.apps.accounts import utils
from govapp.apps.catalogue import models

# Typing
from typing import Any


class IsCatalogueEntryPermissions(permissions.BasePermission):
    """Permissions for the Catalogue Entry ViewSet."""

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
        # Check Action
        if view.action in ("create", "destroy"):
            # Creates and Destroys are not allowed by anyone
            allowed = False

        elif view.action in ("list", "retrieve", "update", "partial_update",
                             "lock", "unlock", "decline", "assign", "unassign"):
            # Retrieves and Lists are always allowed by anyone
            # Updates might be allowed, but we delegate it to `has_object_permission`
            # Locking, Unlocking and Declining might be allowed, but we delegate it to `has_object_permission`
            # Assigning and Unassigning also might be allowed, again we delegate it to `has_object_permission`
            # Re-publishing to GeoServer might be allowed, again we delegate it to `has_object_permission`
            allowed = True

        else:
            # Allow all other actions by default
            # This allows dynamically generated actions such as the custom
            # 'choice' actions to be used by anyone
            allowed = True

        # Return
        return allowed

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
        # Check Action
        if view.action in ("create", "destroy"):
            # Creates and Destroys are not allowed by anyone
            allowed = False

        elif view.action in ("list", "retrieve"):
            # Retrieves and Lists are always allowed by anyone
            allowed = True

        elif view.action in ("update", "partial_update"):
            # Update and Partial Update
            # Check Catalogue Entry specific permissions
            # 1. Object is a Catalogue Entry
            # 2. Catalogue Entry is unlocked
            # 3a. User is an administrator AND is assigned to this entry, OR
            # 3b. User has READ_WRITE access permission on this entry
            allowed = (
                isinstance(obj, models.catalogue_entries.CatalogueEntry)
                and obj.is_unlocked()
                and (
                    (utils.is_administrator(request.user) and obj.assigned_to == request.user)
                    or obj.get_user_access_permission(request.user) == 'read_write'
                )
            )

        elif view.action in ("lock", "unlock", "decline"):
            # Lock, Unlock and Decline
            # 1. Object is a Catalogue Entry
            # 2. User is in the Catalogue Editors group
            # 3. User is one of this Catalogue Entry's editors
            # 4. Catalogue Entry is `assigned_to` this user
            if utils.is_administrator(request.user) is True:
                allowed = True
            else: 
                allowed = (
                    isinstance(obj, models.catalogue_entries.CatalogueEntry)
                    and utils.is_catalogue_editor(request.user)
                    and obj.is_editor(request.user)
                    and obj.assigned_to == request.user
                )
            
        elif view.action in ("assign", "unassign"):
            # Assign and Unassign
            # Assigning or Unassigning a Catalogue Entry has its own set of rules
            # 1. Object is a Catalogue Entry
            # 2. User is in the Catalogue Editors group
            # 3. User is one of this Catalogue Entry's editors
            allowed = (
                isinstance(obj, models.catalogue_entries.CatalogueEntry)
                and utils.is_administrator(request.user)
                #and utils.is_catalogue_editor(request.user)
                #and obj.is_editor(request.user)
            )
            allowed =True
        else:
            # Allow all other actions by default
            # This allows dynamically generated actions such as the custom
            # 'choice' actions to be used by anyone
            allowed = True
        # Return
        return allowed


class HasCatalogueEntryPermissions(permissions.BasePermission):
    """Permissions for the Model with a Catalogue Entry ViewSet."""

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
        # Check Action
        if view.action == "create":
            # Create
            # Check Catalogue Entry specific permissions
            # 1. Request contains a reference to a Catalogue Entry
            # 2. User is in the Catalogue Editor group
            # 3. User is one of this Catalogue Entry's editors
            # 4. Catalogue Entry is `assigned_to` this user
            # 5. Catalogue Entry is unlocked
            catalogue_entry = models.catalogue_entries.CatalogueEntry.from_request(request)

            if utils.is_administrator(request.user) is True:
                allowed = True
            else: 
                allowed = (
                    catalogue_entry is not None                
                    and utils.is_catalogue_editor(request.user)
                    and catalogue_entry.is_editor(request.user)
                    and catalogue_entry.assigned_to == request.user
                    and catalogue_entry.is_unlocked()
                )

        elif view.action in ("destroy", "list", "retrieve", "update", "partial_update"):
            # Destroys might be allowed, but we delegate it to `has_object_permission`
            # Retrieves and Lists are always allowed by anyone
            # Updates might be allowed, but we delegate it to `has_object_permission`
            allowed = True

        else:
            # Allow all other actions by default
            # This allows dynamically generated actions such as the custom
            # 'choice' actions to be used by anyone
            allowed = True

        # Return
        return allowed

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
        # Check Action
        if view.action in ("list", "retrieve"):
            # Retrieves and Lists are always allowed by anyone
            allowed = True

        elif view.action in ("destroy", "update", "partial_update"):
            # Destroy, Update and Partial Update
            # Check Catalogue Entry specific permissions
            # 1. Object has a Catalogue Entry attached to it
            # 2. User is in the Catalogue Editors group
            # 3. User is one of this Catalogue Entry's editors
            # 4. Catalogue Entry is `assigned_to` this user
            # 5. Catalogue Entry is unlocked

            
            allowed = (
                hasattr(obj, "catalogue_entry")
                and isinstance(obj.catalogue_entry, models.catalogue_entries.CatalogueEntry)
                and utils.is_administrator(request.user)
                #and utils.is_catalogue_editor(request.user)
                #and obj.catalogue_entry.is_editor(request.user)
                and obj.catalogue_entry.assigned_to == request.user
                and obj.catalogue_entry.is_unlocked()
            )

        else:
            # Allow all other actions by default
            # This allows dynamically generated actions such as the custom
            # 'choice' actions to be used by anyone
            allowed = True

        # Return
        return allowed
