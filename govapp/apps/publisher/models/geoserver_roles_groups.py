import json
import logging
import reversion

from django.db import models
from django.contrib import auth

from govapp.apps.publisher.models.workspaces import Workspace
from govapp.common import mixins


# Logging
log = logging.getLogger(__name__)


@reversion.register()
class GeoServerRole(mixins.RevisionedMixin):
    name = models.CharField(max_length=255, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "GeoServer Role"
        verbose_name_plural = "GeoServer Roles"

    def __str__(self) -> str:
        return self.name


class GeoServerGroupManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().prefetch_related('geoserver_roles')


@reversion.register()
class GeoServerGroup(mixins.RevisionedMixin):
    name = models.CharField(max_length=255, unique=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    geoserver_roles = models.ManyToManyField(GeoServerRole, through='GeoServerGroupRole', related_name='geoserver_groups')
    objects = GeoServerGroupManager()

    class Meta:
        verbose_name = "GeoServer Group"
        verbose_name_plural = "GeoServer Groups"

    def __str__(self) -> str:
        return self.name


@reversion.register()
class GeoServerGroupRole(mixins.RevisionedMixin):
    geoserver_group = models.ForeignKey(GeoServerGroup, null=True, blank=True, on_delete=models.CASCADE)
    geoserver_role = models.ForeignKey(GeoServerRole, null=True, blank=True, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "GeoServer GroupRole"
        verbose_name_plural = "GeoServer GroupRoles"
    

@reversion.register()
class GeoServerRolePermission(mixins.RevisionedMixin):
    geoserver_role = models.ForeignKey(GeoServerRole, null=True, blank=True, on_delete=models.CASCADE)
    workspace = models.ForeignKey(Workspace, null=True, blank=True, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    write = models.BooleanField(default=False)
    admin = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "GeoServer RolePermission"
        verbose_name_plural = "GeoServer RolePermissions"
    
    def __str__(self) -> str:
        return f'{self.workspace},{self.geoserver_role}, r:{self.read}, w:{self.write}, a:{self.admin}'

    @staticmethod
    def _add_or_update_rule(rules, key, value):
        """
        Add a new key-value pair to the dictionary. If the key already exists,
        append the new value to the existing value, separated by a comma.

        :param rules: Dictionary to update
        :param key: Key to add or update
        :param value: Value to add or append
        """
        if key in rules:
            # Append the new value to the existing value, separated by a comma
            rules[key] = f"{rules[key]},{value}"
        else:
            # Add the new key-value pair to the dictionary
            rules[key] = value
        
        return rules

    @staticmethod
    def get_rules():
        from django.db.models import Prefetch
        CREATE_PERMISSION_FOR_LAYER = False  # Considering the relationship from the current GeoServerRole model to other models, it seems that layer permission is not being taken into account.

        # Prefetch related data to minimize database hits
        permissions = GeoServerRolePermission.objects.filter(active=True).select_related(
            'geoserver_role',
            'workspace'
        ).prefetch_related(
            Prefetch('workspace__publish_channels__publish_entry__catalogue_entry')
        )
        
        rules = {}
        log.info(f'Permissions in the database: [{permissions}]')
        for perm in permissions:
            if perm.workspace:
                # Rules for workspaces
                if perm.read:
                    rules = GeoServerRolePermission._add_or_update_rule(rules, f"{perm.workspace.name}.*.r", perm.geoserver_role.name)
                if perm.write:
                    rules = GeoServerRolePermission._add_or_update_rule(rules, f"{perm.workspace.name}.*.w", perm.geoserver_role.name)
                if perm.admin:
                    rules = GeoServerRolePermission._add_or_update_rule(rules, f"{perm.workspace.name}.*.a", perm.geoserver_role.name)

                if CREATE_PERMISSION_FOR_LAYER:
                    # Rules for layers
                    for geoserver_publish_channel in perm.workspace.publish_channels.all():
                        catalogue_entry = geoserver_publish_channel.publish_entry.catalogue_entry if geoserver_publish_channel.publish_entry and geoserver_publish_channel.publish_entry.catalogue_entry else None
                        if catalogue_entry:
                            log.info(f'Catalogue entry (layer): [{catalogue_entry}] found for the publish_channel: [{geoserver_publish_channel}] under the workspace: [{perm.workspace}].')
                            if perm.read:
                                rules = GeoServerRolePermission._add_or_update_rule(rules, f"{perm.workspace.name}.{catalogue_entry.name}.r", perm.geoserver_role.name)
                            if perm.write:
                                rules = GeoServerRolePermission._add_or_update_rule(rules, f"{perm.workspace.name}.{catalogue_entry.name}.w", perm.geoserver_role.name)
                            # if perm.admin:  # <== No admin type for the layer acl
                            #     rules = GeoServerRolePermission._add_or_update_rule(rules, f"{perm.workspace.name}.{catalogue_entry.name}.a", perm.geoserver_role.name)

        log.info(f'Rules in the database: {json.dumps(rules, indent=4)}')
        return rules


UserModel = auth.get_user_model()

class GeoServerGroupUser(models.Model):
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE)
    geoserver_group = models.ForeignKey(GeoServerGroup, null=True, blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.user_group}"

class GeoServerRoleUser(models.Model):
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE)
    geoserver_role = models.ForeignKey(GeoServerRole, null=True, blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.user_role}"