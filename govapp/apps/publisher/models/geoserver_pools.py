"""Kaartdijin Boodja Publisher Django Application GeoserverPool Models."""


# Third-Party
from django.db import models
from django.forms import ValidationError
from django.contrib.auth import get_user_model
from django.db.models import Q
import reversion
import logging
import httpx
import json
import urllib

# Local
from govapp import settings
from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerGroup, GeoServerGroupUser, GeoServerRole, GeoServerRoleUser
from govapp.common import mixins
from govapp.common.utils import calculate_dict_differences, generate_random_password, handle_http_exceptions

log = logging.getLogger(__name__)
UserModel = get_user_model()


def encode(s):
    # s = urllib.parsquote(s, safe='')
    s = urllib.parse.quote(s) 
    return s


@reversion.register()
class GeoServerPool(mixins.RevisionedMixin):
    """Model for an Geoserver Pool."""
    name = models.CharField(max_length=200, null=True)
    url = models.CharField(max_length=500)
    url_ui = models.URLField(null=True, blank=True)
    username = models.TextField()
    password = models.TextField()
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        """Geoserver Pool Model Metadata."""
        verbose_name = "Geoserver Pool"
        verbose_name_plural = "Geoserver Pools"

    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.id}: {self.name}" if self.name else f'{self.id}'
    
    @property
    def base_url_security(self):
        return f"{self.url}/rest/security"
    
    @property
    def auth(self):
        return (self.username, self.password)

    @property
    def headers_json(self):
        return {"content-type": "application/json","Accept": "application/json"}

    @property
    def total_active_layers(self):
        return self.geoserverpublishchannel_set.filter(active=True).count()

    @property
    def total_inactive_layers(self):
        return self.geoserverpublishchannel_set.exclude(active=True).count()

    @property
    def total_layers(self):
        return self.total_active_layers + self.total_inactive_layers

    def synchronize_groups(self, group_name_list):
        existing_groups = self.get_all_groups()

        # Determine groups to delete (existing groups not in group_name_list)
        groups_to_delete = set(existing_groups) - set(group_name_list)
        for group in groups_to_delete:
            self.delete_existing_group(group)

        # Determine groups to create (groups in group_name_list not in existing groups)
        groups_to_create = set(group_name_list) - set(existing_groups)
        for group in groups_to_create:
            self.create_new_group(group)

    def synchronize_roles(self, role_name_list):
        try:
            # Fetch existing roles from GeoServer
            existing_roles = self.get_all_role()

            # Determine roles to delete (existing roles not in role_name_list)
            roles_to_delete = set(existing_roles) - set(role_name_list)
            for role in roles_to_delete:
                self.delete_existing_role(role)

            # Determine roles to create (roles in role_name_list not in existing roles)
            roles_to_create = set(role_name_list) - set(existing_roles)
            for role in roles_to_create:
                self.create_new_role(role)
        except Exception as e:
            log.error(f'An error occurred during synchronization: {e}')

    ### Workspace
    @handle_http_exceptions(log)
    def get_all_workspaces(self, service_name=''):
        url = f"{self.url}/rest/workspaces"
        response = httpx.get(
            url=url,
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        workspaces = response.json()
        return workspaces['workspaces']['workspace']

    @handle_http_exceptions(log)
    def create_workspace_if_not_exists(self, workspace_name):
        # URL to check the existence of the workspace
        workspace_url = f"{self.url}/rest/workspaces/{workspace_name}.json"

        with httpx.Client(auth=self.auth) as client:
            # Send a GET request to check the existence of the workspace
            response = client.get(workspace_url, headers=self.headers_json)

        # Create the workspace only if it doesn't exist
        if response.status_code == 404:
            log.info(f"Workspace '{workspace_name}' does not exist in the geoserver: [{self.url}]. Creating...")

            # URL to create the workspace
            create_workspace_url = f"{self.url}/rest/workspaces"

            # JSON data required to create the workspace
            workspace_data = {
                "workspace": {
                    "name": workspace_name
                }
            }

            with httpx.Client(auth=self.auth) as client:
                # Send a POST request to create the workspace
                create_response = client.post(create_workspace_url, headers=self.headers_json, json=workspace_data)

            # Check the status code to determine if the creation was successful
            if create_response.status_code == 201:
                log.info(f"Workspace '{workspace_name}' created successfully in the geoserver: [{self.url}].")
            else:
                log.info("Failed to create workspace.")
                log.info(create_response.text)
        else:
            log.info(f"Workspace '{workspace_name}' already exists in the geoserver: [{self.url}].")

    @handle_http_exceptions(log)
    def delete_workspace(self, workspace_name, recurse='false'):
        workspace_url = f"{self.url}/rest/workspaces/{workspace_name}.json?recurse={recurse}"

        with httpx.Client(auth=(self.username, self.password)) as client:
            # Send a GET request to check the existence of the workspace
            response = client.delete(workspace_url, headers=self.headers_json)
        
            if response.status_code == 200:
                log.info(f"Workspace: [{workspace_name}] has been deleted successfully from the GeoServer: [{self}].")
            elif response.status_code == 403:
                log.error(f'Deleting the workspace: [{workspace_name}] from the GeoServer: [{self}], but the workspace or related Namespace is not empty (and recurse not true)')
            elif response.status_code == 404:
                log.error(f'Workspace: [{workspace_name}] does not exist in the GeoServer: [{self}].')
            
            return response

    ### Permission
    def synchronize_rules(self, new_rules):
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
        url = f"{self.base_url_security}/acl/layers.json"
        response = httpx.get(url, auth=self.auth)
        response.raise_for_status()
        rules_data = response.json()
        log.info(f'Successfully fetched ACL rules: [{json.dumps(rules_data, indent=4)}] from the geoserver: [{self}].')
        return rules_data

    @handle_http_exceptions(log)
    def create_rules(self, rules):
        """Add a set of access control rules."""
        url = f"{self.base_url_security}/acl/layers"
        response = httpx.post(url, json=rules, headers=self.headers_json, auth=self.auth)
        response.raise_for_status()
        log.info(f'Successfully added ACL rules: [{json.dumps(rules)}] to the geoserver: [{self}].')
        return {}

    @handle_http_exceptions(log)
    def update_rules(self, rules):
        """Modify a set of access control rules."""
        url = f"{self.base_url_security}/acl/layers"
        response = httpx.put(url, json=rules, headers=self.headers_json, auth=self.auth)
        response.raise_for_status()
        log.info(f'Successfully updated ACL rules: [{json.dumps(rules)}] in the geoserver: [{self}].')
        return {}

    @handle_http_exceptions(log)
    def delete_rule(self, key):
        """Delete a specific access control rule."""
        url = f"{self.base_url_security}/acl/layers/{key}"
        response = httpx.delete(url, auth=self.auth)
        response.raise_for_status()
        log.info(f'Successfully deleted ACL rule: key=[{key}] from the geoserver: [{self}].')
        return {}

    ### User
    @handle_http_exceptions(log)
    def get_all_users(self, service_name=''):
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/users/" if service_name else f"{self.base_url_security}/usergroup/users/"
        response = httpx.get(
            url=url,
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        existing_users = response.json()
        return existing_users['users']

    @handle_http_exceptions(log)
    def update_existing_user(self, user_data, service_name=''):
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/user/{encode(user_data['user']['userName'])}.json" if service_name else f"{self.base_url_security}/usergroup/user/{encode(user_data['user']['userName'])}.json"
        response = httpx.post(
            url=url,
            headers=self.headers_json,
            content=json.dumps(user_data),
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"User: [{user_data['user']['userName']}] has been updated successfully in GeoServer: [{self}].")
        return response

    @handle_http_exceptions(log)
    def create_new_user(self, user_data, service_name=''):
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/users/" if service_name else f"{self.base_url_security}/usergroup/users/"
        response = httpx.post(
            url=url,
            headers=self.headers_json,
            content=json.dumps(user_data),
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"User: [{user_data['user']['userName']}] has been created successfully in the GeoServer: [{self}].")
        return response

    def check_variable(self, variable, variable_name):
        if not variable:
            raise ValidationError(f'{variable_name} cannot be empty string.')

    @handle_http_exceptions(log)
    def delete_existing_user(self, username, service_name=''):
        self.check_variable(username, 'Username')
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/user/{encode(username)}.json" if service_name else f"{self.base_url_security}/usergroup/user/{encode(username)}.json"
        response = httpx.delete(
            url=url,
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"User: [{username}] has been deleted successfully from the GeoServer: [{self}].")
        return response

    @handle_http_exceptions(log)
    def get_about_version(self):
        response = httpx.get(
            url=f"{self.url}/rest/about/version",
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        res = response.json()
        return res

    ### Group
    @handle_http_exceptions(log)
    def get_all_groups(self, service_name=''):
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/groups/" if service_name else f"{self.base_url_security}/usergroup/groups/"
        response = httpx.get(
            url=url,
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        existing_groups = response.json()
        return existing_groups['groups']

    @handle_http_exceptions(log)
    def get_all_groups_for_user(self, username, service_name=''):
        self.check_variable(username, 'Username')
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/user/{encode(username)}/groups" if service_name else f"{self.base_url_security}/usergroup/user/{encode(username)}/groups"
        response = httpx.get(
            url=url,
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        groups_for_user = response.json()
        return groups_for_user['groups']

    @handle_http_exceptions(log)
    def create_new_group(self, group_name, service_name=''):
        self.check_variable(group_name, 'Group name')
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/group/{encode(group_name)}.json" if service_name else f"{self.base_url_security}/usergroup/group/{encode(group_name)}.json"
        response = httpx.post(
            url=url,
            auth=self.auth
        )
        log.info(f"Group: [{group_name}] has been created successfully in the GeoServer: [{self}].")
        return response

    @handle_http_exceptions(log)
    def delete_existing_group(self, group_name, service_name=''):
        self.check_variable(group_name, 'Group name')
        if group_name in settings.NON_DELETABLE_USERGROUPS:
            log.info(f'Group: [{group_name}] cannot be deleted from the geoserver: [{self}]. (USERGROUPS_TO_KEEP: [{settings.NON_DELETABLE_USERGROUPS}])')
            return
        
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/group/{encode(group_name)}.json" if service_name else f"{self.base_url_security}/usergroup/group/{encode(group_name)}.json"
        response = httpx.delete(
            url=url,
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Group: [{group_name}] has been deleted successfully from the GeoServer: [{self}].")
        return response

    @handle_http_exceptions(log)
    def associate_user_with_group(self, username, group_name, service_name=''):
        self.check_variable(username, 'Username')
        self.check_variable(group_name, 'Group name')
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/user/{encode(username)}/group/{encode(group_name)}.json" if service_name else f"{self.base_url_security}/usergroup/user/{encode(username)}/group/{encode(group_name)}.json"
        response = httpx.post(
            url=url,
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"User: [{username}] has been successfully associated with the group: [{group_name}] in the GeoServer: [{self}].")
        return response

    @handle_http_exceptions(log)
    def disassociate_user_from_group(self, username, group_name, service_name=''):
        self.check_variable(username, 'Username')
        self.check_variable(group_name, 'Group name')
        url = f"{self.base_url_security}/usergroup/service/{encode(service_name)}/user/{encode(username)}/group/{encode(group_name)}.json" if service_name else f"{self.base_url_security}/usergroup/user/{encode(username)}/group/{encode(group_name)}.json"
        response = httpx.delete(
            url=url,
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"User: [{username}] has been successfully unassociated from the group: [{group_name}] in the GeoServer: [{self}].")
        return response

    ### Role
    @handle_http_exceptions(log)
    def get_all_roles(self):
        response = httpx.get(
            url=f"{self.base_url_security}/roles/",
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        existing_roles = response.json()
        return existing_roles['roles']
    
    def get_all_roles_for_user(self, username):
        self.check_variable(username, 'Username')
        response = httpx.get(
            url=f"{self.base_url_security}/roles/user/{encode(username)}.json",
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        roles_for_user = response.json()
        return roles_for_user['roles']

    def get_all_roles_for_group(self, group_name):
        self.check_variable(group_name, 'Group name')
        response = httpx.get(
            url=f"{self.base_url_security}/roles/group/{encode(group_name)}.json",
            headers=self.headers_json,
            auth=self.auth
        )
        response.raise_for_status()
        roles_for_group = response.json()
        return roles_for_group['roles']

    def create_new_role(self, role_name):
        self.check_variable(role_name, 'Role name')
        response = httpx.post(
            url=f"{self.base_url_security}/roles/role/{encode(role_name)}.json",
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Role: [{role_name}] has been created successfully in the GeoServer: [{self}].")
        return response

    def delete_existing_role(self, role_name):
        self.check_variable(role_name, 'Role name')
        if role_name in settings.NON_DELETABLE_ROLES:  # We don't want to delete the default group 'ADMIN'
            log.info(f'Role: [{role_name}] cannot be deleted from the geoserver: [{self}]. (ROLES_TO_KEEP: [{settings.NON_DELETABLE_ROLES}])')
            return

        response = httpx.delete(
            url=f"{self.base_url_security}/roles/role/{encode(role_name)}.json",
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Role: [{role_name}] has been deleted successfully in the GeoServer: [{self}].")
        return response

    def associate_role_with_user(self, username, role_name):
        self.check_variable(username, 'Username')
        self.check_variable(role_name, 'Role name')
        response = httpx.post(
            url=f"{self.base_url_security}/roles/role/{encode(role_name)}/user/{encode(username)}.json",
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Role: [{role_name}] has been associated successfully with the user: [{username}] in the GeoServer: [{self}].")
        return response

    def disassociate_role_from_user(self, username, role_name):
        self.check_variable(username, 'Username')
        self.check_variable(role_name, 'Role name')
        response = httpx.delete(
            url=f"{self.base_url_security}/roles/role/{encode(role_name)}/user/{encode(username)}.json",
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Role: [{role_name}] has been disassociated successfully from the user: [{username}] in the GeoServer: [{self}].")
        return response

    def associate_role_with_group(self, role_name, group_name):
        self.check_variable(role_name, 'Role name')
        self.check_variable(group_name, 'Group name')
        response = httpx.post(
            url=f"{self.base_url_security}/roles/role/{encode(role_name)}/group/{encode(group_name)}.json",
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Role: [{role_name}] has been associated successfully with the group: [{group_name}] in the GeoServer: [{self}].")
        return response

    def disassociate_role_from_group(self, role_name, group_name):
        self.check_variable(role_name, 'Role name')
        self.check_variable(group_name, 'Group name')
        response = httpx.delete(
            url=f"{self.base_url_security}/roles/role/{encode(role_name)}/group/{encode(group_name)}.json",
            auth=self.auth
        )
        response.raise_for_status()
        log.info(f"Role: [{role_name}] has been disassociated successfully from the group: [{group_name}] in the GeoServer: [{self}].")
        return response

    def cleanup_users(self):
        log.info(f'Cleaning up users in the geoserver: [{self}]...')

        all_users_in_geoserver = self.get_all_users(settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        all_users_in_kb = UserModel.objects.filter(
            Q(geoserverroleuser__geoserver_role__active=True) |
            Q(geoservergroupuser__geoserver_group__active=True)).distinct()

        for user_in_geoserver in all_users_in_geoserver:
            user_exists_in_kb = any(user_in_geoserver['userName'] == user_in_kb.email for user_in_kb in all_users_in_kb)

            if not user_exists_in_kb and user_exists_in_kb not in settings.NON_DELETABLE_USERS:
                log.info(f'User: [{user_in_geoserver}] exists in the geoserver: [{self}], but not in KB.')
                self.delete_existing_user(user_in_geoserver['userName'], settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)

    def sync_groups(self):
        all_groups_in_kb = set(list(GeoServerGroup.objects.filter(active=True).values_list('name', flat=True)))
        all_groups_in_geoserver = set(self.get_all_groups(settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM))

        groups_only_in_kb = all_groups_in_kb - all_groups_in_geoserver 
        groups_only_in_geoserver = all_groups_in_geoserver - all_groups_in_kb

        for group_name in groups_only_in_kb:
            if group_name not in settings.DEFAULT_USERGROUPS_IN_GEOSERVER:
                self.create_new_group(group_name, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        
        for group_name in groups_only_in_geoserver:
            if group_name not in settings.NON_DELETABLE_USERGROUPS:
                self.delete_existing_group(group_name, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)

    def sync_roles(self):
        all_roles_in_kb = set(list(GeoServerRole.objects.filter(active=True).values_list('name', flat=True)))
        all_roles_in_geoserver = set(self.get_all_roles())

        roles_only_in_kb = all_roles_in_kb - all_roles_in_geoserver 
        roles_only_in_geoserver = all_roles_in_geoserver - all_roles_in_kb

        for role_name in roles_only_in_kb:
            if role_name not in settings.DEFAULT_ROLES_IN_GEOSERVER:
                self.create_new_role(role_name)
        
        for role_name in roles_only_in_geoserver:
            if role_name not in settings.NON_DELETABLE_ROLES:
                self.delete_existing_role(role_name)

    def associate_user_with_groups(self, user):
        group_user_in_kb = GeoServerGroupUser.objects.filter(user=user, geoserver_group__active=True)
        groups_for_user_in_kb = [obj.geoserver_group for obj in group_user_in_kb]
        if groups_for_user_in_kb:
            log.info(f'Group(s): [{groups_for_user_in_kb}] found for the user: [{user.email}] in the KB')
        else:
            log.info(f'No groups found for the user: [{user.email}] in the KB')

        all_groups_in_geoserver = self.get_all_groups(settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        if all_groups_in_geoserver:
            log.info(f'Group(s): [{all_groups_in_geoserver}] found in the geoserver: [{self}].')
        else:
            log.info(f'No groups found in the geoserver: [{self}].')

        groups_for_user_in_geoserver = self.get_all_groups_for_user(user.email, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        if groups_for_user_in_geoserver:
            log.info(f'Group(s): [{groups_for_user_in_geoserver}] for the user: [{user.email}] found in the geoserver: [{self}].')
        else:
            log.info(f'No groups for the user: [{user.email}] found in the geoserver: [{self}].')

        for group_in_kb in groups_for_user_in_kb:
            group_associated = any(group_in_kb.name == group_in_geoserver for group_in_geoserver in groups_for_user_in_geoserver)
            if group_associated:
                log.info(f'Group: [{group_in_kb.name}] is already associated with the user: [{user.email}] in the geoserver: [{self}].')
            else:
                log.info(f'Group: [{group_in_kb.name}] is not associated with the user: [{user.email}] in the geoserver: [{self}].')
                group_exists = any(group_in_kb.name == group_in_geoserver for group_in_geoserver in all_groups_in_geoserver)
                if not group_exists:
                    log.info(f'Group: [{group_in_kb.name}] does not exist in the geoserver: [{self}].')
                    self.create_new_group(group_in_kb.name, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
                self.associate_user_with_group(user.email, group_in_kb.name, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        return groups_for_user_in_kb

    def disassociate_user_from_groups(self, user, groups_for_user_in_kb):
        groups_for_user_in_geoserver = self.get_all_groups_for_user(user.email, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        if groups_for_user_in_geoserver:
            log.info(f'Group(s): [{groups_for_user_in_geoserver}] for the user: [{user.email}] found in the geoserver: [{self}].')
        else:
            log.info(f'No groups for the user: [{user.email}] found in the geoserver: [{self}].')

        for group_in_geoserver in groups_for_user_in_geoserver:
            group_associated = any(group_in_geoserver == group_in_kb.name for group_in_kb in groups_for_user_in_kb)
            if not group_associated:
                log.info(f'Group: [{group_in_geoserver}] is associated with the user: [{user.email}] in the geoserver: [{self}], but not in KB')
                self.disassociate_user_from_group(user.email, group_in_geoserver, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)

    def disassociate_user_from_roles(self, user, roles_for_user_in_kb):
        roles_for_user_in_geoserver = self.get_all_roles_for_user(user.email)
        if roles_for_user_in_geoserver:
            log.info(f'Role(s): [{roles_for_user_in_geoserver}] found for the user: [{user.email}] in the geoserver: [{self}].')
        else:
            log.info(f'No roles found for the user: [{user.email}] in the geoserver: [{self}].')

        for role_in_geoserver in roles_for_user_in_geoserver:
            role_associated = any(role_in_geoserver == role_in_kb.name for role_in_kb in roles_for_user_in_kb)
            if not role_associated:
                log.info(f'Role: [{role_in_geoserver}] is associated with the user: [{user.email}] in the geoserver: [{self}], but not in KB')
                self.disassociate_role_from_user(user.email, role_in_geoserver)

    def associate_user_with_roles(self, user):
        role_user_in_kb = GeoServerRoleUser.objects.filter(user=user, geoserver_role__active=True)
        roles_for_user_in_kb = [obj.geoserver_role for obj in role_user_in_kb]
        if roles_for_user_in_kb:
            log.info(f'Role(s): [{roles_for_user_in_kb}] found for the user: [{user.email}] in the geoserver: [{self}].')
        else:
            log.info(f'No roles found for the user: [{user.email}] in the geoserver: [{self}].')

        all_roles_in_geoserver = self.get_all_roles()
        if all_roles_in_geoserver:
            log.info(f'Role(s): [{all_roles_in_geoserver}] found in the geoserver: [{self}].')
        else:
            log.info(f'No roles found in the geoserver: [{self}].')

        roles_for_user_in_geoserver = self.get_all_roles_for_user(user.email)
        if roles_for_user_in_geoserver:
            log.info(f'Role(s): [{roles_for_user_in_geoserver}] for the user: [{user.email}] found in the geoserver: [{self}].')
        else:
            log.info(f'No roles for the user: [{user.email}] found in the geoserver: [{self}].')

        for role_in_kb in roles_for_user_in_kb:
            role_associated = any(role_in_kb.name == role_in_geoserver for role_in_geoserver in roles_for_user_in_geoserver)
            if role_associated:
                log.info(f'Role: [{role_in_kb.name}] is already associated with the user: [{user.email}] in the geoserver: [{self}].')
            else:
                log.info(f'Role: [{role_in_kb.name}] is not associated with the user: [{user.email}] in the geoserver: [{self}].')
                role_exists = any(role_in_kb.name == role_in_geoserver for role_in_geoserver in all_roles_in_geoserver)
                if not role_exists:
                    log.info(f'Role: [{role_in_kb.name}] does not exist in the geoserver: [{self}].')
                    self.create_new_role(role_in_kb.name)
                self.associate_role_with_user(user.email, role_in_kb.name)
        return roles_for_user_in_kb

    def create_or_update_user(self, user):
        """Create or update a user in GeoServer."""
        user_data = {
            "user": {
                "userName": user.email,
                "password": generate_random_password(50),
                "enabled": user.is_active
            }
        }

        # Check if user already exists
        existing_users = self.get_all_users(settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        user_exists = any(user_in_geoserver['userName'] == user_data['user']['userName'] for user_in_geoserver in existing_users)

        # Create/Update user
        if user_exists:
            log.info(f'User: [{user.email}] exists in the geoserver: [{self}]')
            response = self.update_existing_user(user_data, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)
        else:
            log.info(f'User: [{user.email}] does not exist in the geoserver: [{self}]')
            response = self.create_new_user(user_data, settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM)

        response.raise_for_status()

    def sync_users_groups_users_roles(self):
        """Synchronize users-groups and users-roles with GeoServer."""
        log.info(f'Synchronize users-groups and users-roles in the geoserver: [{self}]...')

        # Retrieve only users associated with active roles or groups
        users = UserModel.objects.filter(
            Q(geoserverroleuser__geoserver_role__active=True) |
            Q(geoservergroupuser__geoserver_group__active=True)).distinct()

        log.info(f'Users associated with active GeoServerRole or GeoServerGroup: [{users}]')

        # Sync all the groups
        self.sync_groups()

        # Sync all the roles
        self.sync_roles()

        for user in users:
            if not user.email:
                log.warning(f'User: [ID: {user.id}, username: {user.username}, first_name: {user.first_name}, last_name: {user.last_name}] does not have email address.  Skip the geoserver process for this user.')
                continue
            self.create_or_update_user(user)

            # Sync relations between users and groups
            groups_for_user_in_kb = self.associate_user_with_groups(user)
            self.disassociate_user_from_groups(user, groups_for_user_in_kb)

            # Sync relations between users and roles
            roles_for_user_in_kb = self.associate_user_with_roles(user)
            self.disassociate_user_from_roles(user, roles_for_user_in_kb)

    def sync_relations_groups_roles(self, group_in_kb):
        # Associate group with roles
        roles_for_group_in_kb = group_in_kb.geoserver_roles.all()
        log.info(f'Role(s): [{roles_for_group_in_kb}] for the group: [{group_in_kb.name}] found in the KB')

        all_roles_in_geoserver = self.get_all_roles()
        log.info(f'Role(s): [{all_roles_in_geoserver}] found in the geoserver: [{self}].')

        roles_for_group_in_geoserver = self.get_all_roles_for_group(group_in_kb.name)
        log.info(f'Role(s): [{roles_for_group_in_geoserver}] found for the group: [{group_in_kb.name}] in the geoserver: [{self}].')

        for role_in_kb in roles_for_group_in_kb:
            role_associated = any(role_in_kb.name == role_in_geoserver for role_in_geoserver in roles_for_group_in_geoserver)
            if role_associated:
                log.info(f'Role: [{role_in_kb.name}] is already associated with the group: [{group_in_kb.name}] in the geoserver: [{self}].')
            else:
                log.info(f'Role: [{role_in_kb.name}] is not associated with the group: [{group_in_kb.name}] in the geoserver: [{self}].')
                role_exists = any(role_in_kb.name == role_in_geoserver for role_in_geoserver in all_roles_in_geoserver)
                if not role_exists:
                    log.info(f'Role: [{role_in_kb.name}] does not exist in the geoserver: [{self}].')
                    self.create_new_role(role_in_kb.name)
                self.associate_role_with_group(role_in_kb.name, group_in_kb.name)

        # Disassociate group from roles
        all_roles_in_geoserver = self.get_all_roles()
        log.info(f'Role(s): [{all_roles_in_geoserver}] found in the geoserver: [{self}].')

        roles_for_group_in_geoserver = self.get_all_roles_for_group(group_in_kb.name)  # Update list
        log.info(f'Role(s): [{roles_for_group_in_geoserver}] found for the group: [{group_in_kb.name}] in the geoserver: [{self}].')

        for role_in_geoserver in roles_for_group_in_geoserver:
            role_associated = any(role_in_geoserver == role_in_kb.name for role_in_kb in roles_for_group_in_kb)
            if not role_associated:
                log.info(f'Role: [{role_in_geoserver}] is associated with the group: [{group_in_kb.name}] in the geoserver: [{self}], but not in KB')
                self.disassociate_role_from_group(role_in_geoserver, group_in_kb.name)

    def sync_groups_roles(self):
        """Synchronize groups-roles with GeoServer."""
        log.info(f'Synchronize groups-roles in the geoserver: [{self}]...')

        groups_in_kb = GeoServerGroup.objects.filter(active=True)
        log.info(f'Group(s): [{groups_in_kb}] found in the KB.')

        for group_in_kb in groups_in_kb:
            self.sync_relations_groups_roles(group_in_kb)


class GeoserverClusterPool(models.Model):
    """
    Model representing a server node within a GeoServer pool.
    This implementation follows the initial specifications.
    """

    geoserver_pool = models.ForeignKey(
        'GeoServerPool',
        on_delete=models.CASCADE,
        related_name='cluster_nodes'
    )

    server_url = models.CharField(max_length=500)
    username = models.CharField(max_length=200)
    password = models.CharField(max_length=200)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Node for {self.geoserver_pool.name} at {self.server_url}"

    class Meta:
        verbose_name = "GeoServer Cluster Pool Node"
        verbose_name_plural = "GeoServer Cluster Pool Nodes"
