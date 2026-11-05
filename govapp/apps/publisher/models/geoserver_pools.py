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
import copy
import xml.etree.ElementTree as ET

# Local
from govapp import settings
from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerGroup, GeoServerGroupUser, GeoServerRole, GeoServerRoleUser
from govapp.common import mixins
from govapp.common.utils import calculate_dict_differences, handle_http_exceptions

log = logging.getLogger(__name__)
UserModel = get_user_model()

# Each write to a user/group service makes GeoServer save and reload the whole user file,
# which takes many seconds when it holds thousands of users. The httpx default is 5 seconds.
GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS = 60


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

    # Set on the unsaved copies returned by targets()
    cluster_name = ""
    is_target_copy = False
    
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
        text = f"{self.id}: {self.name}" if self.name else f'{self.id}'
        return f"{text} [{self.cluster_name}]" if self.cluster_name else text

    def save(self, *args, **kwargs):
        if self.is_target_copy:
            raise RuntimeError("A GeoServer pool target copy must not be saved.")
        super().save(*args, **kwargs)

    def targets(self) -> list["GeoServerPool"]:
        """Returns the GeoServers that GeoServer calls for this pool must reach.

        If the pool has cluster nodes with a name, each enabled named node is one
        geocluster, and a copy of the pool with that node's URL and credentials is
        returned for each. The list is empty when all named nodes are disabled.
        Otherwise the pool itself is returned, as before.
        """
        named_nodes = self.cluster_nodes.exclude(name="")
        if not named_nodes.exists():
            return [self]

        targets = []
        for node in named_nodes.filter(enabled=True).order_by("name"):
            target = copy.copy(self)
            target.url = node.server_url
            target.username = node.username
            target.password = node.password
            target.cluster_name = node.name
            target.is_target_copy = True
            targets.append(target)
        return targets

    @classmethod
    def enabled_targets(cls) -> list["GeoServerPool"]:
        """Returns the targets of every enabled pool."""
        return [target for pool in cls.objects.filter(enabled=True) for target in pool.targets()]
    
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

    ### Resource (files in the GeoServer data directory)
    @handle_http_exceptions(log)
    def get_resource(self, path):
        """Read a file in the GeoServer data directory, e.g. 'security/usergroup/dbca/config.xml'."""
        self.check_variable(path, 'Resource path')
        response = httpx.get(
            url=f"{self.url}/rest/resource/{encode(path)}",
            auth=self.auth
        )
        response.raise_for_status()
        return response.content

    @handle_http_exceptions(log)
    def put_resource(self, path, content, content_type='application/xml'):
        """Write a file in the GeoServer data directory in one request, replacing the old one."""
        self.check_variable(path, 'Resource path')
        response = httpx.put(
            url=f"{self.url}/rest/resource/{encode(path)}",
            headers={"Content-Type": content_type},
            content=content,
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        log.info(f"Resource: [{path}] has been written successfully in the GeoServer: [{self}].")
        return response

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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
        )
        response.raise_for_status()
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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
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
            auth=self.auth,
            timeout=GEOSERVER_USERGROUP_WRITE_TIMEOUT_SECONDS
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

    @staticmethod
    def build_usergroup_file():
        """Return the content of the GeoServer user file (users.xml format) built from KB data.

        Users: everyone with an email address who is in an active group or has an active role,
        without a password (users log in through SSO). Groups: every active group with its members.
        Everything is sorted, so the same data always gives the same bytes.
        """
        users = {}
        for user in UserModel.objects.filter(
                Q(geoservergroupuser__geoserver_group__active=True) |
                Q(geoserverroleuser__geoserver_role__active=True)).exclude(email__isnull=True).exclude(email='').distinct():
            # Two KB users can share an email address: enable the GeoServer user if either is active
            users[user.email] = users.get(user.email, False) or user.is_active

        members = {}
        for group_user in GeoServerGroupUser.objects.filter(geoserver_group__active=True).exclude(user__email__isnull=True).exclude(user__email=''):
            members.setdefault(group_user.geoserver_group.name, set()).add(group_user.user.email)

        root = ET.Element('userRegistry', {'xmlns': 'http://www.geoserver.org/security/users', 'version': '1.0'})
        users_element = ET.SubElement(root, 'users')
        for email in sorted(users):
            ET.SubElement(users_element, 'user', {'enabled': 'true' if users[email] else 'false', 'name': email})
        groups_element = ET.SubElement(root, 'groups')
        for group_name in sorted(GeoServerGroup.objects.filter(active=True).values_list('name', flat=True)):
            group_element = ET.SubElement(groups_element, 'group', {'enabled': 'true', 'name': group_name})
            for email in sorted(members.get(group_name, ())):
                ET.SubElement(group_element, 'member', {'username': email})

        log.info(f'User file built: [{len(users)}] user(s), [{len(groups_element)}] group(s).')
        return ET.tostring(root, encoding='utf-8', xml_declaration=True)

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

    def sync_usergroup_file(self):
        """Write the KB users and groups to the GeoServer user file in one request.

        The whole file of the custom user/group service is replaced through the resource REST API,
        instead of one REST call per user. GeoServer reloads the file by itself when the service's
        checkInterval is above 0. Returns True when the file was written, False when it was
        already up to date.
        """
        service_name = settings.GEOSERVER_USERGROUP_SERVICE_NAME_CUSTOM
        config = ET.fromstring(self.get_resource(f'security/usergroup/{service_name}/config.xml'))
        file_name = config.findtext('fileName')
        check_interval = int(config.findtext('checkInterval') or 0)
        if not file_name:
            raise ValueError(f'The user/group service: [{service_name}] in the geoserver: [{self}] has no fileName.')
        if check_interval <= 0:
            raise ValueError(f'The checkInterval of the user/group service: [{service_name}] in the geoserver: [{self}] is [{check_interval}], so GeoServer would not reload the user file.  Set the file reload interval in the GeoServer UI.')

        path = f'security/usergroup/{service_name}/{file_name}'
        content = self.build_usergroup_file()
        if self.get_resource(path) == content:
            log.info(f'User file: [{path}] in the geoserver: [{self}] is up to date.')
            return False

        self.put_resource(path, content)
        return True

    def sync_user_roles(self):
        """Synchronize the roles linked directly to users with GeoServer.

        GeoServer REST cannot list the users of a role, so the role file of the default role
        service is read once through the resource API, and only the differences with KB are sent
        through REST. Only KB users are touched, and never NON_DELETABLE_USERS (e.g. admin).
        A user that fails is logged and skipped. Returns the names of the users that failed.
        """
        log.info(f'Synchronize users-roles in the geoserver: [{self}]...')

        # Sync all the roles
        self.sync_roles()

        # Roles linked directly to users in GeoServer
        config = ET.fromstring(self.get_resource('security/role/default/config.xml'))
        role_file = ET.fromstring(self.get_resource(f"security/role/default/{config.findtext('fileName')}"))
        namespace = '{http://www.geoserver.org/security/roles}'
        roles_in_geoserver = {
            user_roles.get('username'): {role_ref.get('roleID') for role_ref in user_roles.findall(f'{namespace}roleRef')}
            for user_roles in role_file.iter(f'{namespace}userRoles')
        }

        # Roles linked directly to users in KB
        roles_in_kb = {}
        for role_user in GeoServerRoleUser.objects.filter(geoserver_role__active=True).exclude(user__email__isnull=True).exclude(user__email=''):
            roles_in_kb.setdefault(role_user.user.email, set()).add(role_user.geoserver_role.name)

        kb_emails = set(UserModel.objects.exclude(email__isnull=True).exclude(email='').values_list('email', flat=True))
        failed_usernames = []
        for username in sorted(set(roles_in_kb) | (set(roles_in_geoserver) & kb_emails)):
            if username in settings.NON_DELETABLE_USERS:
                continue
            roles_wanted = roles_in_kb.get(username, set())
            roles_current = roles_in_geoserver.get(username, set())
            try:
                for role_name in sorted(roles_wanted - roles_current):
                    self.associate_role_with_user(username, role_name)
                for role_name in sorted(roles_current - roles_wanted):
                    self.disassociate_role_from_user(username, role_name)
            except httpx.HTTPError as e:
                failed_usernames.append(username)
                log.error(f'Failed to sync the roles of the user: [{username}] to the geoserver: [{self}]: {e}')

        return failed_usernames

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

    # A node with a name is one geocluster; a node with a blank name is only used for tile cache purge.
    name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Geocluster name, e.g. prod1. Must match KB_CLUSTER_CODE of that geocluster's "
            "geoserver manager. Leave blank for a node used only for tile cache purge."
        ),
    )

    def __str__(self):
        return f"Node for {self.geoserver_pool.name} at {self.server_url}"

    class Meta:
        verbose_name = "GeoServer Cluster Pool Node"
        verbose_name_plural = "GeoServer Cluster Pool Nodes"
        constraints = [
            models.UniqueConstraint(
                fields=["geoserver_pool", "name"],
                condition=~Q(name=""),
                name="unique_cluster_node_name_per_pool",
                violation_error_message="A cluster node with this name already exists in this GeoServer pool.",
            ),
        ]
