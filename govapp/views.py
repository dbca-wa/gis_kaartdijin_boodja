"""Django project views."""


# Third-Party
import os
from django import http
from django import shortcuts
from django.views.generic import base
from django.contrib import auth
from django.utils.decorators import method_decorator
from rest_framework.decorators import permission_classes
from owslib.wms import WebMapService
import json

# Internal
from govapp import settings
from govapp.apps.catalogue.models import catalogue_entries as catalogue_entries_models
from govapp.apps.catalogue.models.permission import CatalogueEntryAccessPermission
from govapp.apps.publisher.models import publish_entries as publish_entries_models
from govapp.apps.catalogue.models import custodians as custodians_models
from govapp.apps.publisher.models import workspaces as publish_workspaces_models
from govapp.apps.catalogue.models import layer_metadata as catalogue_layer_metadata_models
from govapp.apps.catalogue.models import layer_submissions as catalogue_layer_submissions_models
from govapp.apps.catalogue.models import layer_subscriptions as catalogue_layer_subscription_models
from govapp.apps.catalogue import utils as catalogue_utils
from govapp.apps.accounts import utils

# Typing
from typing import Any

from govapp.apps.publisher.models.geoserver_pools import GeoServerPool, GeoServerGroup, GeoServerGroupUser
from govapp.apps.publisher.models.publish_channels import GeoServerPublishChannel, StoreType

UserModel = auth.get_user_model()


class HomePage(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/home.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the HomePage view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        # Construct Context
        context: dict[str, Any] = {}
        return http.HttpResponseRedirect('/catalogue/entries/')
        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)


class OldCatalogueVue(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/home.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the HomePage view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        # Construct Context
        context: dict[str, Any] = {}

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)


class PendingImportsView(base.TemplateView):
    template_name = "govapp/pending_imports.html"

    @method_decorator(utils.check_option_menus_permission)
    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        pathToFolder = settings.PENDING_IMPORT_PATH
        file_list = os.listdir(pathToFolder)

        context = {'file_list': file_list}
        return shortcuts.render(request, self.template_name, context)


class ManagementCommandsView(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/management_commands.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        # Construct Context
        context: dict[str, Any] = {}

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)


class PublishPage(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/publish.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the HomePage view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        # For bulk-updated data, if the 'active' field contains 'Null', set it to 'True'
        GeoServerPublishChannel.objects.filter(active__isnull=True).update(active=True)

        # Construct Context
        context: dict[str, Any] = {}
        pe_list = []
        catalogue_entry_list = []

        # START - To be improved later todo a reverse table join      
        ce_obj = catalogue_entries_models.CatalogueEntry.objects.all().order_by('id')
        pe_obj = publish_entries_models.PublishEntry.objects.all()

        for pe in pe_obj:            
            pe_list.append(pe.catalogue_entry.id)

        for ce in ce_obj:
            if ce.id not in pe_list:
                catalogue_entry_list.append({'id': ce.id, 'name': ce.name, 'type': catalogue_entries_models.CatalogueEntryType.get_as_string(ce.type)})
                   
        is_administrator = utils.is_administrator(request.user)

        # END - To be improved later todo a reverse table join    
        context['catalogue_entry_list'] = catalogue_entry_list
        context['is_administrator'] = is_administrator

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)
    

class PublishView(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/publish_view.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the HomePage view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        # Construct Context
        context: dict[str, Any] = {}
        has_edit_access = False
        pe_list = []
        catalogue_entry_list = []
        custodians_obj = custodians_models.Custodian.objects.all()
        publish_entry_obj = publish_entries_models.PublishEntry.objects.get(id=self.kwargs['pk'])
        publish_workspaces = publish_workspaces_models.Workspace.objects.all()
        publish_workspace_list = [{'id': ws.id, 'name': ws.name} for ws in publish_workspaces]
        geoserver_pools = GeoServerPool.objects.filter(enabled=True)
        store_types = dict(StoreType.choices)

        ### START - To be improved later todo a reverse table join      
        # This code lists CatalogueEntries not associated with any PublishEntry, along with CatalogueEntries associated with a specific PublishEntry.
        ce_obj = catalogue_entries_models.CatalogueEntry.objects.all()
        pe_obj = publish_entries_models.PublishEntry.objects.all()

        for pe in pe_obj:            
            pe_list.append(pe.catalogue_entry.id)

        for ce in ce_obj:
            if ce.id not in pe_list:
                catalogue_entry_list.append({'id': ce.id, 'name': ce.name})
                  
            if publish_entry_obj.catalogue_entry:  
                if ce.id == publish_entry_obj.catalogue_entry.id:
                    catalogue_entry_list.append({'id': ce.id, 'name': ce.name})
        ### END - To be improved later todo a reverse table join     

        system_users_list = []
        # system_users_obj = UserModel.objects.filter(is_active=True, groups__name=conf.settings.GROUP_ADMINISTRATOR_NAME)
        system_users_obj = UserModel.objects.filter(is_active=True, groups__name=settings.GROUP_ADMINISTRATORS)
        for su in system_users_obj:
            system_users_list.append({'first_name': su.first_name, 'last_name': su.last_name, 'id': su.id, 'email': su.email})

        geoserver_pool_list = {}
        for gsp in geoserver_pools:
            geoserver_pool_list[gsp.id] = gsp.name
                
        is_administrator = utils.is_administrator(request.user)
        if is_administrator is True and  publish_entry_obj.status == 2 and request.user == publish_entry_obj.assigned_to:
            has_edit_access = True

        show_lock_unlock_btn = False
        if is_administrator is True and request.user == publish_entry_obj.assigned_to:
            show_lock_unlock_btn = True

        context['catalogue_entry_list'] = catalogue_entry_list
        context['publish_entry_obj'] = publish_entry_obj

        context['publishable_to_geoserver'] = publish_entry_obj.publishable_to_geoserver
        context['publishable_to_cddp'] = publish_entry_obj.publishable_to_cddp
        context['publishable_to_ftp'] = publish_entry_obj.publishable_to_ftp

        context['num_of_geoserver_publish_channels_active'] = publish_entry_obj.num_of_geoserver_publish_channels_active
        context['num_of_geoserver_publish_channels_inactive'] = publish_entry_obj.num_of_geoserver_publish_channels_inactive
        context['num_of_ftp_publish_channels'] = publish_entry_obj.num_of_ftp_publish_channels
        context['num_of_cddp_publish_channels'] = publish_entry_obj.num_of_cddp_publish_channels

        context['custodians_obj'] = custodians_obj
        context['system_users'] = system_users_list
        context['publish_id'] = self.kwargs['pk']
        context['has_edit_access'] = has_edit_access
        context['show_lock_unlock_btn'] = show_lock_unlock_btn
        context['publish_workspaces'] = publish_workspaces
        context['publish_workspace_list'] = publish_workspace_list
        context['geoserver_pools'] = geoserver_pools
        context['geoserver_pool_list_json'] = json.dumps(geoserver_pool_list)
        context['store_types'] = store_types
    
        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)
        

class CatalogueEntriesPage(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/catalogue_entries.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the HomePage view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        # Construct Context
        context: dict[str, Any] = {}
        pe_list = []
        catalogue_entry_list = []

        debug = request.GET.get('debug', False)

        # START - To be improved later todo a reverse table join      
        ce_obj = catalogue_entries_models.CatalogueEntry.objects.all()
        pe_obj = publish_entries_models.PublishEntry.objects.all()

        for pe in pe_obj:            
            pe_list.append(pe.catalogue_entry.id)

        for ce in ce_obj:
            if debug == 'true':
                catalogue_entry_list.append({'id': ce.id, 'name': ce.name})
            else:
                if ce.id not in pe_list:
                    catalogue_entry_list.append({'id': ce.id, 'name': ce.name})

        ce_types_to_display = settings.CATALOGUE_ENTRY_TYPE_TO_DISPLAY       
                
        # END - To be improved later todo a reverse table join    
        context['catalogue_entry_list'] = catalogue_entry_list
        context['tab'] = 'catalogue_entries'
        context['ce_types_to_display'] = ce_types_to_display

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)
    

class CatalogueEntriesView(base.TemplateView):
    """Home page view."""

    # Template name
    template_name = "govapp/catalogue_entries_view.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the HomePage view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        # Construct Context
        context: dict[str, Any] = {}
        catalogue_id = self.kwargs['pk']
        display_symbology_definition_tab = False
        catalogue_layer_metadata = None

        custodians_obj = custodians_models.Custodian.objects.all()
        catalogue_entry_obj = catalogue_entries_models.CatalogueEntry.objects.get(id=self.kwargs['pk'])

        ### Retirieve users for the assigned_to list
        system_users_dict = {}
        # Users in the GROUP_ADMINISTRATORS
        system_users_obj = UserModel.objects.filter(is_active=True, groups__name=settings.GROUP_ADMINISTRATORS)
        for su in system_users_obj:
            system_users_dict[su.id] = {
                'first_name': su.first_name,
                'last_name': su.last_name,
                'id': su.id,
                'email': su.email
            }
        # Users who have permissions to this catalogue_entry_obj
        for permission in catalogue_entry_obj.catalogue_permissions.filter(active=True, access_permission=CatalogueEntryAccessPermission.READ_WRITE):
            system_users_dict[permission.user.id] = {
                'first_name': permission.user.first_name, 
                'last_name': permission.user.last_name, 
                'id': permission.user.id, 
                'email': permission.user.email
            }
        read_write_users = [system_users_dict[key] for key in system_users_dict]
        
        user_access_permission = catalogue_entry_obj.get_user_access_permission(request.user)
        is_administrator = utils.is_administrator(request.user)
        is_assigned = True if catalogue_entry_obj.assigned_to == request.user else False
        has_read_write_access = True if is_administrator or user_access_permission == 'read_write' else False

        has_edit_access = False  # True: user can edit right now
        if has_read_write_access:
            if is_assigned:
                if catalogue_entry_obj.status in [
                    catalogue_entries_models.CatalogueEntryStatus.NEW_DRAFT,
                    catalogue_entries_models.CatalogueEntryStatus.DRAFT,
                    catalogue_entries_models.CatalogueEntryStatus.PENDING,
                ]:
                    has_edit_access = True
        
        layer_symbology = catalogue_entry_obj.symbology if hasattr(catalogue_entry_obj, 'symbology') else ''
        
        # Symbology tab
        if catalogue_entry_obj.type == catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_QUERY:
            display_symbology_definition_tab = True
        elif catalogue_entry_obj.type == catalogue_entries_models.CatalogueEntryType.SPATIAL_FILE and not catalogue_entry_obj.file_extension.lower() in ['.tif', '.tiff',]:
            display_symbology_definition_tab = True

        # Attribute table tab
        display_attribute_table_tab = True
        if catalogue_entry_obj.type in [catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_WMS, catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_WFS,]:
            display_attribute_table_tab = False
        elif catalogue_entry_obj.file_extension.lower() in ['.tif', '.tiff',]:
            display_attribute_table_tab = False

        # Metadata tab
        display_metadata_tab = True
        if catalogue_entry_obj.type in [catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_WMS, catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_WFS,]:
            display_metadata_tab = False

        # Layer Submission tab
        display_layer_submission_tab = True
        if catalogue_entry_obj.type in [catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_WMS, catalogue_entries_models.CatalogueEntryType.SUBSCRIPTION_WFS,]:
            display_layer_submission_tab = False

        catalogue_layer_metadata_obj = catalogue_layer_metadata_models.LayerMetadata.objects.filter(catalogue_entry=catalogue_id)
        if catalogue_layer_metadata_obj.count() > 0:
            catalogue_layer_metadata = catalogue_layer_metadata_obj[0]

        # context['catalogue_entry_list'] = catalogue_entry_list
        context['catalogue_entry_obj'] = catalogue_entry_obj
        context['custodians_obj'] = custodians_obj
        context['read_write_users'] = read_write_users
        context['catalogue_entry_id'] = self.kwargs['pk']
        context['tab'] = self.kwargs['tab']
        context['display_attribute_table_tab'] = display_attribute_table_tab
        context['display_symbology_definition_tab'] = display_symbology_definition_tab
        context['display_metadata_tab'] = display_metadata_tab
        context['display_layer_submission_tab'] = display_layer_submission_tab
        context['layer_symbology'] = layer_symbology
        context['catalogue_layer_metadata'] = catalogue_layer_metadata
        context['is_administrator'] = is_administrator
        context['is_assigned'] = is_assigned
        context['has_read_write_access'] = has_read_write_access
        context['has_edit_access'] = has_edit_access
        context['user_access_permission'] = user_access_permission
        context['CatalogueEntryAccessPermission'] = CatalogueEntryAccessPermission  # READ, READ_WRITE
        context['CatalogueEntryType'] = catalogue_entries_models.CatalogueEntryType  # SPATIAL_FILE, SUBSCRIPTION_WFS, ...
        context['CatalogueEntryPermissionType'] = catalogue_entries_models.CatalogueEntryPermissionType  # NOT_RESTRICTED, RESTRICTED
        context['CatalogueEntryStatus'] = catalogue_entries_models.CatalogueEntryStatus  # NEW_DRAFT, LOCKED, ...

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)


class LayerSubmission(base.TemplateView):
    """Layer Submissions view."""

    # Template name
    template_name = "govapp/layer_submissions.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the Submissions view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """

        # Construct Context
        context: dict[str, Any] = {}
        context['tab'] = 'layer_submission'

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)    
    

class LayerSubmissionView(base.TemplateView):
    """Layer Submissions view."""

    # Template name
    template_name = "govapp/layer_submissions_view.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the SubmissionsView view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        pk = self.kwargs['pk']
        layer_submission = catalogue_layer_submissions_models.LayerSubmission.objects.get(id=pk)
        user_access_permission = layer_submission.get_user_access_permission(request.user)

        is_administrator = utils.is_administrator(request.user)

        # Calculate accessibility to download link
        accessible_to_download = False
        if layer_submission.permission_type == catalogue_entries_models.CatalogueEntryPermissionType.NOT_RESTRICTED:
            accessible_to_download = True
        elif layer_submission.permission_type == catalogue_entries_models.CatalogueEntryPermissionType.RESTRICTED:
            if is_administrator or user_access_permission in ['read', 'read_write']:
                accessible_to_download = True

        # Calculate accessibility to the Map
        accessible_to_map = accessible_to_download

        # Construct Context
        context: dict[str, Any] = {}
        context['tab'] = self.kwargs['tab']
        context['layer_submission_obj'] = layer_submission
        context['user_access_permission'] = user_access_permission
        context['accessible_to_download'] = accessible_to_download
        context['accessible_to_map'] = accessible_to_map
        context['CatalogueEntryAccessPermission'] = CatalogueEntryAccessPermission
        context['CatalogueEntryPermissionType'] = catalogue_entries_models.CatalogueEntryPermissionType
        context['id'] = layer_submission.catalogue_entry.id

        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)   
    
    # def get_layer_file(request: http.HttpRequest, pk:int):
    #     layer_submission = catalogue_layer_submissions_models.LayerSubmission.objects.get(id=pk)
    #     file_name = os.path.basename(layer_submission.geojson)
    #     with open(layer_submission.geojson, 'rb') as file:
    #         response = http.FileResponse(file)
    #         response['Content-Disposition'] = f'attachment; filename="{file_name}"'
    #         return response
    

class LayerSubscriptions(base.TemplateView):
    """Layer Subscriptions page."""

    # Template name
    template_name = "govapp/layer_subscriptions.html"
      
    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the Subscription.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        is_administrator = False
        if utils.is_administrator(request.user) is True:
                is_administrator = True
                
        # Construct Context
        context: dict[str, Any] = {}
        context['is_administrator'] = is_administrator
        context['tab'] = "layer_subscriptions"
        
        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)   
    
class LayerSubscriptionsView(base.TemplateView):
    """Layer Submissions view."""

    # Template name
    template_name = "govapp/layer_subscriptions_view.html"
    
    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        """Provides the GET request endpoint for the Subscription view.

        Args:
            request (http.HttpRequest): The incoming HTTP request.
            *args (Any): Extra positional arguments.
            **kwargs (Any): Extra keyword arguments.

        Returns:
            http.HttpResponse: The rendered template response.
        """
        
        pk = self.kwargs['pk']
        subscription_obj = catalogue_layer_subscription_models.LayerSubscription.objects.get(id=pk)
        LayerSubscriptionStatus = catalogue_layer_subscription_models.LayerSubscriptionStatus
        LayerSubscriptionType = catalogue_layer_subscription_models.LayerSubscriptionType
        
        system_users_list = []
        # system_users_obj = UserModel.objects.filter(is_active=True, groups__name=conf.settings.GROUP_ADMINISTRATOR_NAME)
        system_users_obj = UserModel.objects.filter(is_active=True, groups__name=settings.GROUP_ADMINISTRATORS)
        for su in system_users_obj:
            system_users_list.append({'first_name': su.first_name, 'last_name': su.last_name, 'id': su.id, 'email': su.email})
        has_edit_access = False
        if utils.is_administrator(request.user) is True and request.user == subscription_obj.assigned_to:
             if subscription_obj.status in (LayerSubscriptionStatus.DRAFT, LayerSubscriptionStatus.NEW_DRAFT, LayerSubscriptionStatus.PENDING):
                has_edit_access = True
        is_assigned = True if subscription_obj.assigned_to == request.user else False
        
        # Construct Context
        context: dict[str, Any] = {}
        context['subscription_obj'] = subscription_obj
        context['status'] = catalogue_utils.find_enum_by_value(LayerSubscriptionStatus, subscription_obj.status).name.replace('_', ' ')
        context['system_users'] = system_users_list
        context['is_system_user'] = utils.is_administrator(request.user)
        context['has_edit_access'] = has_edit_access
        context['type'] = catalogue_utils.find_enum_by_value(LayerSubscriptionType, subscription_obj.type).name.replace('_', ' ')
        context['workspaces'] = publish_workspaces_models.Workspace.objects.all()
        context['enabled_js'] = "true" if subscription_obj.enabled else "false"
        context['is_assigned'] = is_assigned
        
        # Render Template and Return
        return shortcuts.render(request, self.template_name, context)        
    

class GeoServerQueue(base.TemplateView):
    """ GeoServer Queue to show Geoserver Queue status """
    
    # Template name
    template_name = "govapp/geoserverqueue.html"


class CDDPQueueView(base.TemplateView):
    """ Show CDDP Queue status """
    
    # Template name
    template_name = "govapp/cddpqueue.html"


class GeoServerGroupsView(base.TemplateView):
    template_name = "govapp/usergroups.html"


class GeoServerLayerHealthcheckView(base.TemplateView):
    template_name = "govapp/geoserver_layer_healthcheck.html"


class GeoServerGroupView(base.TemplateView):
    template_name = "govapp/usergroup.html"

    def get(self, request: http.HttpRequest, *args: Any, **kwargs: Any) -> http.HttpResponse:
        usergroup_id = self.kwargs['pk']
        geoserver_group = GeoServerGroup.objects.get(id=usergroup_id)

        # roles_related = geoserver_group.geoserver_roles
        # geoserver_group_users = GeoServerGroupUser.objects.filter(geoserver_group=geoserver_group)
        # users_related = [geoserver_group_user.user.email for geoserver_group_user in geoserver_group_users]

        context = {
            'geoserver_group': geoserver_group,
            # 'roles_related': roles_related,
            # 'users_related': users_related,
        }

        return shortcuts.render(request, self.template_name, context)