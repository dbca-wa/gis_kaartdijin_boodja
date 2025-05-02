"""Kaartdijin Boodja Catalogue Django Application Layer Subscription Models."""


# Third-Party
from django.db import models
from django.contrib import auth
from django.contrib.auth import models as auth_models
from django.core.cache import cache
from django import conf
from rest_framework.exceptions import ValidationError
import reversion
import logging

from typing import Union, Optional

# Local
from govapp.apps.catalogue import utils as catalogue_utils
from govapp.common import mixins
from govapp.apps.catalogue.models import catalogue_entries
from govapp.apps.catalogue import notifications as notifications_utils
from govapp.apps.accounts import utils as accounts_utils
from govapp.apps.publisher.models import workspaces
from govapp.apps.publisher.models import publish_entries

# Shortcuts
UserModel = auth.get_user_model()

logger = logging.getLogger(__name__)
    

class LayerSubscriptionType(models.IntegerChoices):
    """Enumeration for a Layer Subscription Status."""
    WMS = 1
    WFS = 2
    POST_GIS = 3

class LayerSubscriptionStatus(models.IntegerChoices):
    """Enumeration for a Layer Subscription Status."""
    NEW_DRAFT = 1
    LOCKED = 2
    DECLINED = 3
    DRAFT = 4
    PENDING = 5

    
@reversion.register()
class LayerSubscription(mixins.RevisionedMixin):
    """Model for a Layer Subscription."""
    DISABLE = 'disable'
    ALLOW = 'allow'
    PREFER = 'prefer'
    REQUIRE = 'require'
    VERIFY_CA = 'verify-ca'
    VERIFY_FULL = 'verify-full'

    SSL_MODE_CHOICES = [
        (DISABLE, 'DISABLE'),
        (ALLOW, 'ALLOW'),
        (PREFER, 'PREFER'),
        (REQUIRE, 'REQUIRE'),
        (VERIFY_CA, 'VERIFY_CA'),
        (VERIFY_FULL, 'VERIFY_FULL'),
    ]
    type = models.IntegerField(choices=LayerSubscriptionType.choices)
    # status = models.IntegerField(choices=LayerSubscriptionStatus.choices, default=LayerSubscriptionStatus.ACTIVE)
    name = models.TextField()
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    url = models.URLField(null=True) # for WMS or WFS
    username = models.CharField(null=True, max_length=100)
    userpassword = models.CharField(null=True, max_length=100)
    connection_timeout = models.IntegerField(default=10000) # ms
    max_connections = models.IntegerField(default=1, null=True) # for WMS or POST GIS
    min_connections = models.IntegerField(default=1, null=True) # for POST GIS
    read_timeout = models.IntegerField(default=10000, null=True) # ms, for WMS
    ssl_mode = models.CharField(max_length=10, choices=SSL_MODE_CHOICES, default=ALLOW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # catalogue_entry = models.OneToOneField(
    #     catalogue_entries.CatalogueEntry,
    #     related_name="subscription",
    #     on_delete=models.CASCADE,
    #     null=True)
    workspace = models.ForeignKey(
        workspaces.Workspace,
        related_name="workspace",
        on_delete=models.CASCADE)
    host = models.CharField(max_length=1000, null=True) # for POST GIS
    port = models.IntegerField(null=True) # for POST GIS
    database = models.CharField(max_length=100, null=True) # for POST GIS
    schema = models.CharField(max_length=100, null=True) # for POST GIS
    fetch_size = models.IntegerField(default=1000, null=True) # for POST GIS
    status = models.IntegerField(choices=LayerSubscriptionStatus.choices, default=LayerSubscriptionStatus.NEW_DRAFT)
    assigned_to = models.ForeignKey(
        UserModel,
        default=None,
        blank=True,
        null=True,
        related_name="assigned_user_subscription",
        on_delete=models.SET_NULL,
    )
    
    # Type Hints for Reverse Relations
    # These aren't exactly right, but are useful for catching simple mistakes.
    publish_entry: "Optional[publish_entries.PublishEntry]"

    class Meta:
        """Layer Subscription Model Metadata."""
        verbose_name = "Layer Subscription"
        verbose_name_plural = "Layer Subscriptions"

    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.id}: {self.name}"

    # @property
    # def name(self) -> str:
    #     """Proxies the Layer Subscription's name to this model.

    #     Returns:
    #         str: Name of the Layer Subscription.
    #     """
    #     # Retrieve and Return
    #     return self.catalogue_entry.name
    
    # @property
    # def description(self) -> str:
    #     """Proxies the Layer Subscription's description to this model.

    #     Returns:
    #         str: Description of the Layer Subscription.
    #     """
    #     # Retrieve and Return
    #     return self.catalogue_entry.description
    
    def is_locked(self) -> bool:
        """Determines whether the Layer Subscription is locked.

        Returns:
            bool: Whether the Layer Subscription is locked.
        """
        # Check and Return
        return self.status == LayerSubscriptionStatus.LOCKED

    def is_pending(self) -> bool:
        """Determines whether the Layer Subscription is locked (pending).

        Returns:
            bool: Whether the Layer Subscription is locked (pending).
        """
        # Check and Return
        return self.status == LayerSubscriptionStatus.PENDING

    def is_declined(self) -> bool:
        """Determines whether the Layer Subscription is declined.

        Returns:
            bool: Whether the Layer Subscription is declined.
        """
        # Check and Return
        return self.status == LayerSubscriptionStatus.DECLINED

    def is_unlocked(self) -> bool:
        """Determines whether the Layer Subscription is unlocked.

        Returns:
            bool: Whether the Layer Subscription is unlocked.
        """
        # Check and Return
        return self.status in (LayerSubscriptionStatus.DRAFT, LayerSubscriptionStatus.NEW_DRAFT, LayerSubscriptionStatus.PENDING)

    def is_new(self) -> bool:
        """Determines whether the Layer Subscription is a new draft.

        Returns:
            bool: Whether the Layer Subscription is a new draft.
        """
        # Check and Return
        return self.status == LayerSubscriptionStatus.NEW_DRAFT

    def is_editor(self, user: Union[auth_models.User, auth_models.AnonymousUser]) -> bool:
        """Checks whether the user is one of this Layer Subscription's editors.

        Args:
            user (Union[models.User, models.AnonymousUser]): User to be checked

        Returns:
            bool: Whether the user is one of this CataloguE entry's editors.
        """
        # Check and Return
        return self.editors.all().filter(id=user.id).exists()

    def lock(self) -> bool:
        """Locks the Layer Subscription.

        Returns:
            bool: Whether the locking was successful.
        """
        # Check Layer Subscription
        if not self.is_unlocked():
            return False
        
        # # Check if Layer Subscription is new
        # if self.is_new():
        #     # Lock the currently active layer
        #     self.active_layer.accept()

        # Set Layer Subscription to Locked
        self.status = LayerSubscriptionStatus.LOCKED

        # Check for Publish Entry
        if hasattr(self, "publish_entry"):
            # Publish Symbology
            self.publish_entry.publish(symbology_only=True)  # type: ignore[union-attr]

        # Save the Layer Subscription
        self.save()

        # Send Emails
        mapped_catalogue_entries = catalogue_entries.CatalogueEntry.objects.filter(layer_subscription=self)
        for catalogue_entry in mapped_catalogue_entries:
            notifications_utils.catalogue_entry_lock(catalogue_entry)
        
        # Success!
        return True
    

    def unlock(self) -> bool:
        """Unlocks the Layer Subscription.

        Returns:
            bool: Whether unlocking was successful.
        """
        # Check Layer Subscription
        if self.is_locked() or self.is_pending():
            # Set Layer Subscription to Draft
            self.status = LayerSubscriptionStatus.DRAFT
            self.save()

            # Success!
            return True

        # Failed
        return False

    def save(self, *args, **kwargs):
        cache.delete(conf.settings.POST_GIS_CACHE_KEY + str(self.id))
        super(LayerSubscription, self).save(*args, **kwargs)
        

    # def decline(self) -> bool:
    #     """Declines the Layer Subscription.

    #     Returns:
    #         bool: Whether the declining was successful.
    #     """
    #     # Check Layer Subscription
    #     if self.is_unlocked():
    #         # Check if Layer Subscription is new
    #         if self.is_new():
    #             # Decline the currently active layer
    #             self.active_layer.decline()

    #         # Set Layer Subscription to Declined
    #         self.status = catalogue_entries.CatalogueEntryStatus.DECLINED
    #         self.save()

    #         # Success!
    #         return True

    #     # Failed
    #     return False

    def assign(self, user: auth_models.User) -> bool:
        """Assigns a user to the Layer Subscription if applicable.

        Args:
            user (auth_models.User): User to be assigned.

        Returns:
            bool: Whether the assigning was successful.
        """
        # Check if the user can be assigned
        # To be assigned, a user must be:
        # 1. In the Catalogue Editors group
        # 2. One of this Layer Subscription's editors
        # if accounts_utils.is_catalogue_editor(user) and self.is_editor(user):
        #     pass
        if accounts_utils.is_administrator(user):
            # Assign user
            self.assigned_to = user
            self.save()

            # Success!
            return True

        # Failed
        return False

    def unassign(self) -> bool:
        """Unassigns the Layer Subscription's user if applicable.

        Returns:
            bool: Whether the unassigning was successful.
        """
        # Check if there is an assigned user
        if self.assigned_to is not None:
            # Unassign
            self.assigned_to = None
            self.save()

            # Success!
            return True

        # Failed
        return False


@reversion.register()
class LayerSubscriptionData(mixins.RevisionedMixin):
    layer_subscription = models.ForeignKey(LayerSubscription, null=True, blank=True, on_delete=models.SET_NULL)
    metadata_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Layer Subscription Data"
        verbose_name_plural = "Layer Subscription Data"

    @classmethod
    def get_latest_by_layer_subscription(cls, layer_subscription):  # latest_data = LayerSubscriptionData.get_latest_by_layer_subscription(layer_subscription_instance)
        layer_subscription_data = cls.objects.filter(layer_subscription=layer_subscription).order_by('-updated_at').first()
        if layer_subscription_data:
            return layer_subscription_data.metadata_json
        else:
            return None
    
    @classmethod
    def retrieve_latest_data(cls, subscription_obj, force_to_query=False):
        if force_to_query:
            # Perform query to WMS, WFS, PostGIS
            metadata_json = cls._retrieve_data_by_query(subscription_obj)
            return metadata_json
        else:
            # Retrieve the latest record from LayerSubscriptionData
            metadata_json = cls.get_latest_by_layer_subscription(subscription_obj)
            if metadata_json:
                logger.info(f'Metadata_json has been retrieved from the Database for the layer subscription: [{subscription_obj}].')
                return metadata_json
            else:
                # Perform query to WMS, WFS, Post_gis
                metadata_json = cls._retrieve_data_by_query(subscription_obj)
                return metadata_json

    @classmethod
    def _retrieve_data_by_query(cls, subscription_obj):
        try:
            if subscription_obj.type == LayerSubscriptionType.WMS:
                metadata_json = catalogue_utils.get_wms(subscription_obj.url, subscription_obj.username, subscription_obj.userpassword)
                logger.info(f'Metadata_json has been retrieved from the WMS for the layer subscription: [{subscription_obj}].')
            elif subscription_obj.type == LayerSubscriptionType.WFS:
                metadata_json = catalogue_utils.get_wfs(subscription_obj.url, subscription_obj.username, subscription_obj.userpassword)
                logger.info(f'Metadata_json has been retrieved from the WFS for the layer subscription: [{subscription_obj}].')
            elif subscription_obj.type == LayerSubscriptionType.POST_GIS:
                metadata_json = catalogue_utils.get_post_gis(subscription_obj.host, subscription_obj.database, subscription_obj.username, subscription_obj.userpassword, subscription_obj.port, subscription_obj.schema)
                logger.info(f'Metadata_json has been retrieved from the PostGIS for the layer subscription: [{subscription_obj}].')
            else:
                msg = f'Something wrong with the type of the layer subscription: [{subscription_obj}].'
                logger.error(msg)
                raise ValidationError(msg)

            # Store the data
            layer_subscription_data = cls.objects.create(
                    layer_subscription=subscription_obj,
                    metadata_json=metadata_json,
                )
            logger.info(f'LayerSubscriptionData: [{layer_subscription_data}] has been created.')

            return metadata_json
        except Exception as e:
            logger.error(f"Unable to perform query to WMS/WFS/PostGIS for the layer subscription: [{subscription_obj}]: [{e}]")
