"""Kaartdijin Boodja Accounts Django Application Utility Functions."""


from datetime import datetime
from math import ceil

# Third-Party
import os
import re
import functools
from django import conf
import django
from django.contrib import auth
from django.contrib.auth import models
from django.db.models import query
from django.core.exceptions import PermissionDenied
import govapp

# Typing
from typing import Iterable, Union

import logging
from django.conf import settings
from django.template.loader import render_to_string
from django.core.exceptions import ObjectDoesNotExist


# Configure logging
logger = logging.getLogger(__name__)

# Shortcuts
UserModel = auth.get_user_model()


def can_view_option_menus(user):
    return user.is_superuser or user.is_staff


def check_option_menus_permission(view_func):
    def wrapper(request, *args, **kwargs):
        if can_view_option_menus(request.user):
            return view_func(request, *args, **kwargs)
        else:
            raise PermissionDenied
    return wrapper


def all_administrators() -> Iterable[models.User]:
    """Retrieves all of the administrator users.

    Yields:
        models.User: Users in the administrator group.
    """
    # Retrieve and Yield
    group = django.contrib.auth.models.Group.objects.get(name=settings.GROUP_ADMINISTRATORS)
    yield from UserModel.objects.filter(
        # groups__id=conf.settings.GROUP_ADMINISTRATOR_ID
        groups__id=group.id
    )


def all_catalogue_editors() -> Iterable[models.User]:
    """Retrieves all of the administrator users.

    Yields:
        models.User: Users in the administrator group.
    """
    # Retrieve and Yield
    group = django.contrib.auth.models.Group.objects.get(name=settings.GROUP_CATALOGUE_EDITORS)
    yield from UserModel.objects.filter(
        # groups__id=conf.settings.GROUP_CATALOGUE_EDITOR_ID
        groups__id=group.id
    )


def is_administrator(user: Union[models.User, models.AnonymousUser]) -> bool:
    """Checks whether a user is an Administrator.

    Args:
        user (Union[models.User, models.AnonymousUser]): User to be checked.

    Returns:
        bool: Whether the user is in the Administrator group.
    """
    # Check and Return
    group = django.contrib.auth.models.Group.objects.get(name=settings.GROUP_ADMINISTRATORS)
    return (
        not isinstance(user, models.AnonymousUser)  # Must be logged in
        # and user.groups.filter(id=conf.settings.GROUP_ADMINISTRATOR_ID).exists()  # Must be in group
        and user.groups.filter(id=group.id).exists()  # Must be in group
    )


def is_catalogue_editor(user: Union[models.User, models.AnonymousUser]) -> bool:
    """Checks whether a user is a Catalogue Editor.

    Args:
        user (Union[models.User, models.AnonymousUser]): User to be checked.

    Returns:
        bool: Whether the user is in the Catalogue Editor group.
    """
    # Check and Return
    group = django.contrib.auth.models.Group.objects.get(name=settings.GROUP_CATALOGUE_EDITORS)
    return (
        not isinstance(user, models.AnonymousUser)  # Must be logged in
        # and user.groups.filter(id=conf.settings.GROUP_CATALOGUE_EDITOR_ID).exists()  # Must be in group
        and user.groups.filter(id=group.id).exists()  # Must be in group
    )


def is_catalogue_admin(user: Union[models.User, models.AnonymousUser]) -> bool:
    # Check and Return
    return (
        not isinstance(user, models.AnonymousUser)  # Must be logged in
        and user.groups.filter(name=settings.GROUP_CATALOGUE_ADMIN).exists()  # Must be in group
    )


def is_api_user(user: Union[models.User, models.AnonymousUser]) -> bool:
    # Check and Return
    return (
        not isinstance(user, models.AnonymousUser)  # Must be logged in
        and user.groups.filter(name=settings.GROUP_API_USER).exists()  # Must be in group
    )


def limit_to_administrators() -> query.Q:
    """Limits a fields choice to only objects in the Administrators group.

    Returns:
        query.Q: Query to limit object to those in the Administrators group.
    """
    # Construct Query and Return
    group = django.contrib.auth.models.Group.objects.get(name=settings.GROUP_ADMINISTRATORS)
    # return query.Q(groups__pk=conf.settings.GROUP_ADMINISTRATOR_ID)
    return query.Q(groups__pk=group.id)


def limit_to_catalogue_editors() -> query.Q:
    """Limits a fields choice to only objects in the Catalogue Editors group.

    Returns:
        query.Q: Query to limit object to those in the Catalogue Editors group.
    """
    # Construct Query and Return
    group = django.contrib.auth.models.Group.objects.get(name=settings.GROUP_CATALOGUE_EDITORS)
    # return query.Q(groups__pk=conf.settings.GROUP_CATALOGUE_EDITOR_ID)
    return query.Q(groups__pk=group.id)


def hash_password(password):
    """
    Convert Django's hashed password to a GeoServer-compatible format.
    Here we use SHA-256 and Base64 encoding
    """
    try:
        # Assuming password is in Django's 'pbkdf2_sha256' format and removing the scheme
        hashed = password.split('$')[-1]
        return f"crypt1:{hashed}"
    except Exception as e:
        logger.error(f"Password hashing error: {e}")
        raise


def exception_handler_decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ObjectDoesNotExist as e:
            logger.error(f"Database object not found: {e}")
            raise
        except Exception as e:
            logger.error(f"An error occurred in {func.__name__}: {e}")
            raise
    return wrapper


@exception_handler_decorator
def generate_security_config_file(usergroup_service_names):
    this_config_filename = 'config.xml'
        
    # Render the template with the data
    rendered_xml = render_to_string('govapp/geoserver/security/config_template.xml', {
        'auth_provider_names': usergroup_service_names
    })
    cleaned_xml = remove_blank_lines(rendered_xml)

    # Save file
    save_path = os.path.join(govapp.settings.GEOSERVER_SECURITY_FILE_PATH, this_config_filename)
    save_contents_to_file(cleaned_xml, save_path)


@exception_handler_decorator
def generate_auth_files(usergroup_service_name):
    authentication_provider_name = usergroup_service_name
    this_config_filename = 'config.xml'

    # Render the template with the data
    rendered_xml = render_to_string('govapp/geoserver/security/auth/config_template.xml', {
        'authentication_provider_name': authentication_provider_name,
        'usergroup_service_name': usergroup_service_name, 
    })
    cleaned_xml = remove_blank_lines(rendered_xml)

    # Save file
    save_path = os.path.join(govapp.settings.GEOSERVER_SECURITY_FILE_PATH, 'auth', authentication_provider_name, this_config_filename)
    save_contents_to_file(cleaned_xml, save_path)


def generate_usergroup_files(usergroup_service_name, users_xml_filename):
    generate_user_config_xml_file(usergroup_service_name, users_xml_filename)
    generate_users_xsd_file(usergroup_service_name)
    generate_users_xml_files(usergroup_service_name, users_xml_filename)


@exception_handler_decorator
def generate_user_config_xml_file(usergroup_service_name, users_xml_filename):
    file_name = 'config.xml'

    # Render the template with the data
    rendered_xml = render_to_string('govapp/geoserver/security/usergroup/config_template.xml', {
        'usergroup_service_name': usergroup_service_name, 
        'users_xml_filename': users_xml_filename
    })
    cleaned_xml = remove_blank_lines(rendered_xml)

    # Save file
    save_path = os.path.join(govapp.settings.GEOSERVER_SECURITY_FILE_PATH, 'usergroup', usergroup_service_name, file_name)
    save_contents_to_file(cleaned_xml, save_path)


@exception_handler_decorator
def generate_users_xsd_file(usergroup_service_name):
    file_name = 'users.xsd'

    # Render the template with the data
    rendered_xml = render_to_string('govapp/geoserver/security/usergroup/users_template.xsd', {
    })
    cleaned_xml = remove_blank_lines(rendered_xml)

    # Save file
    save_path = os.path.join(govapp.settings.GEOSERVER_SECURITY_FILE_PATH, 'usergroup', usergroup_service_name, file_name)
    save_contents_to_file(cleaned_xml, save_path)


@exception_handler_decorator
def generate_users_xml_files(usergroup_service_name, users_xml_filename):
    """
    Generate the users.xml file from the Django models using a Django template.
    
    :param output_path: Path where the generated users.xml should be saved.
    """
    from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerGroup, GeoServerGroupUser, GeoServerRole, GeoServerRoleUser
    # Fetch all active users
    users = UserModel.objects.filter(is_active=True)
    
    # Fetch all active groups
    groups = GeoServerGroup.objects.filter(active=True)
    
    # Fetch all active roles
    roles = GeoServerRole.objects.filter(active=True)

    # Prepare user data
    user_data = [{
        'name': user.email,  # Assuming email is used as username
        'password': hash_password(user.password)  # GeoServer needs hashed passwords
    } for user in users]

    # Prepare group data
    group_data = []
    for group in groups:
        members = GeoServerGroupUser.objects.filter(geoserver_group=group).values_list('user__email', flat=True)
        group_data.append({
            'name': group.name,
            'members': list(members)
        })

    # Prepare role data
    role_data = []
    for role in roles:
        users_in_role = GeoServerRoleUser.objects.filter(geoserver_role=role).values_list('user__email', flat=True)
        role_data.append({
            'name': role.name,
            'users': list(users_in_role)
        })

    # Render the template with the data
    rendered_xml = render_to_string('govapp/geoserver/security/usergroup/users_template.xml', {
        'users': user_data,
        'groups': group_data,
        'roles': role_data
    })
    cleaned_xml = remove_blank_lines(rendered_xml)

    # Save file
    save_path = os.path.join(govapp.settings.GEOSERVER_SECURITY_FILE_PATH, 'usergroup', usergroup_service_name, users_xml_filename)
    save_contents_to_file(cleaned_xml, save_path)


@exception_handler_decorator
def generate_role_files(role_service_name='default', roles_xml_file_name='roles.xml'):
    """
    Generate the roles.xml file from the Django models using a Django template.
    
    :param file_name: Name of the output file.
    """
    from govapp.apps.publisher.models.geoserver_roles_groups import GeoServerGroup, GeoServerGroupUser, GeoServerRole, GeoServerRoleUser

    # Fetch all active roles
    roles = GeoServerRole.objects.filter(active=True)
    
    # Prepare role data
    role_data = []
    for role in roles:
        # Define parent role ID if any
        role_data.append({
            'id': role.name,
            'parent_id': role.parent_role.name if role.parent_role else None
        })

    # Prepare user-role data
    user_roles = []
    users = UserModel.objects.filter(is_active=True)
    for user in users:
        user_role_ids = GeoServerRoleUser.objects.filter(user=user).values_list('geoserver_role__name', flat=True)
        user_roles.append({
            'username': user.email,  # Assuming email is used as username
            'roles': list(user_role_ids)
        })

        # default user: 'admin' has a default role 'ADMIN'
        for relation in settings.DEFAULT_USER_ROLES:
            for user, roles in relation.items():
                user_roles.append({
                    'username': user,
                    'roles': list(roles)
                })

    # Prepare group-role data
    group_roles = []
    groups = GeoServerGroup.objects.filter(active=True)
    for group in groups:
        group_role_ids = group.geoserver_roles.values_list('name', flat=True)
        group_roles.append({
            'groupname': group.name,
            'roles': list(group_role_ids)
        })

    # Render the template with the data
    rendered_xml = render_to_string('govapp/geoserver/security/role/roles_template.xml', {
        'roles': role_data,
        'user_roles': user_roles,
        'group_roles': group_roles
    })
    cleaned_xml = remove_blank_lines(rendered_xml)

    # Save file
    save_path = os.path.join(govapp.settings.GEOSERVER_SECURITY_FILE_PATH, 'role', role_service_name, roles_xml_file_name)
    save_contents_to_file(cleaned_xml, save_path)


def save_contents_to_file(cleaned_xml, save_path):
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, 'w', encoding='utf-8') as output_file:
        output_file.write(cleaned_xml)
        logger.info(f"File: [{save_path}] has been successfully generated.")


def remove_blank_lines(text):
    """
    Remove blank lines from a string.
    
    :param text: The input string.
    :return: A string with blank lines removed.
    """
    return re.sub(r'\n\s*\n', '\n', text)


def get_file_list(config_path):
    file_list = []
    datetime_format = '%d-%m-%Y %H:%M:%S'
    num_of_files = 0
    # Normalise config_path: remove trailing slash so the prefix-stripping
    # logic below always works regardless of how the setting is configured.
    config_path = config_path.rstrip('/')
        # Recursively collect all files
    for dirpath, _, filenames in os.walk(config_path):
        num_of_files += len(filenames)
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            dirpath_removed = filepath[len(config_path + '/'):] if filepath.startswith(config_path + '/') else filepath
            file_stat = os.stat(filepath)
            creation_time = datetime.fromtimestamp(file_stat.st_ctime).strftime(datetime_format)
            last_access_time = datetime.fromtimestamp(file_stat.st_atime).strftime(datetime_format)
            last_modify_time = datetime.fromtimestamp(file_stat.st_mtime).strftime(datetime_format)
            size_bytes = file_stat.st_size
            size_kb = ceil(file_stat.st_size / 1024)
            file_list.append({
                    'filepath': dirpath_removed,
                    'created_at': creation_time,
                    'last_accessed_at': last_access_time,
                    'last_modified_at': last_modify_time,
                    'size_bytes': size_bytes,
                    'size_kb': size_kb
                })
    return file_list, num_of_files



def user_can_view_logs(user):
    """
    Checks if a given user has permission to view the logs.
    
    Returns True if the user is a superuser or belongs to one of the
    groups specified in settings.py.
    """
    # 1. The user must be authenticated to have properties like is_superuser or groups.
    if not user.is_authenticated:
        return False

    # 2. Grant access immediately if the user is a superuser.
    if user.is_superuser:
        return True

    # 3. Check for group membership.
    return user.groups.filter(name__in=settings.ALLOWED_GROUPS_TO_VIEW_LOGFILE).exists()