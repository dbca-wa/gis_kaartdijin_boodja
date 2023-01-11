"""Kaartdijin Boodja Catalogue Django Application Catalogue Entry Models."""


# Third-Party
from django.contrib import auth
from django.contrib.auth import models as auth_models
from django.db import models
from rest_framework import request
import reversion

# Local
from . import custodians
from .. import mixins
from .. import utils
from ...accounts import utils as accounts_utils

# Typing
from typing import TYPE_CHECKING, Optional, Union

# Type Checking
if TYPE_CHECKING:
    from . import layer_attributes
    from . import layer_metadata
    from . import layer_submissions
    from . import layer_subscriptions
    from . import layer_symbology
    from . import notifications


# Shortcuts
UserModel = auth.get_user_model()


class CatalogueEntryStatus(models.IntegerChoices):
    """Enumeration for a Catalogue Entry Status."""
    NEW_DRAFT = 1
    LOCKED = 2
    DECLINED = 3
    DRAFT = 4
    PENDING = 5


@reversion.register(
    follow=(
        "attributes",
        "metadata",
        "layers",
        "symbology",
        "email_notifications",
        "webhook_notifications",
    )
)
class CatalogueEntry(mixins.RevisionedMixin):
    """Model for a Catalogue Entry."""
    name = models.TextField()
    description = models.TextField()
    status = models.IntegerField(choices=CatalogueEntryStatus.choices, default=CatalogueEntryStatus.NEW_DRAFT)
    updated_at = models.DateTimeField(auto_now=True)
    editors = models.ManyToManyField(UserModel)
    custodian = models.ForeignKey(
        custodians.Custodian,
        default=None,
        blank=True,
        null=True,
        related_name="custody",
        on_delete=models.SET_NULL,
    )
    assigned_to = models.ForeignKey(
        UserModel,
        default=None,
        blank=True,
        null=True,
        related_name="assigned",
        on_delete=models.SET_NULL,
    )

    # Type Hints for Reverse Relations
    # These aren't exactly right, but are useful for catching simple mistakes.
    attributes: "models.Manager[layer_attributes.LayerAttribute]"
    layers: "models.Manager[layer_submissions.LayerSubmission]"
    metadata: "layer_metadata.LayerMetadata"
    subscription: "layer_subscriptions.LayerSubscription"
    symbology: "layer_symbology.LayerSymbology"
    email_notifications: "models.Manager[notifications.EmailNotification]"
    webhook_notifications: "models.Manager[notifications.WebhookNotification]"

    class Meta:
        """Catalogue Entry Model Metadata."""
        verbose_name = "Catalogue Entry"
        verbose_name_plural = "Catalogue Entries"

    def __str__(self) -> str:
        """Provides a string representation of the object.

        Returns:
            str: Human readable string representation of the object.
        """
        # Generate String and Return
        return f"{self.name}"

    @property
    def active_layer(self) -> "layer_submissions.LayerSubmission":
        """Retrieves the currently active layer.

        Returns:
            layer_submissions.LayerSubmission: The currently active layer.
        """
        # Retrieve Active Layer
        active_layer = self.layers.filter(is_active=True).last()

        # Check
        assert active_layer is not None, f"{repr(self)} has no active layer"  # noqa: S101

        # Return
        return active_layer

    @classmethod
    def from_request(cls, request: request.Request) -> Optional["CatalogueEntry"]:
        """Retrieves a possible Catalogue Entry from request data.

        Args:
            request (request.Request): Request to retrieve Catalogue Entry from.

        Returns:
            Optional[models.catalogue_entries.CatalogueEntry]: Catalogue Entry.
        """
        # Retrieve Possible Catalogue Entry and Return
        return cls.objects.filter(
            id=request.data.get("catalogue_entry", -1),  # -1 Sentinel Value for Non-Existent Catalogue Entry
        ).first()

    def is_locked(self) -> bool:
        """Determines whether the Catalogue Entry is locked.

        Returns:
            bool: Whether the Catalogue Entry is locked.
        """
        # Check and Return
        return self.status == CatalogueEntryStatus.LOCKED

    def is_pending(self) -> bool:
        """Determines whether the Catalogue Entry is locked (pending).

        Returns:
            bool: Whether the Catalogue Entry is locked (pending).
        """
        # Check and Return
        return self.status == CatalogueEntryStatus.PENDING

    def is_declined(self) -> bool:
        """Determines whether the Catalogue Entry is declined.

        Returns:
            bool: Whether the Catalogue Entry is declined.
        """
        # Check and Return
        return self.status == CatalogueEntryStatus.DECLINED

    def is_unlocked(self) -> bool:
        """Determines whether the Catalogue Entry is unlocked.

        Returns:
            bool: Whether the Catalogue Entry is unlocked.
        """
        # Check and Return
        return self.status in (CatalogueEntryStatus.DRAFT, CatalogueEntryStatus.NEW_DRAFT)

    def is_new(self) -> bool:
        """Determines whether the Catalogue Entry is a new draft.

        Returns:
            bool: Whether the Catalogue Entry is a new draft.
        """
        # Check and Return
        return self.status == CatalogueEntryStatus.NEW_DRAFT

    def is_editor(self, user: Union[auth_models.User, auth_models.AnonymousUser]) -> bool:
        """Checks whether the user is one of this Catalogue Entry's editors.

        Args:
            user (Union[models.User, models.AnonymousUser]): User to be checked

        Returns:
            bool: Whether the user is one of this CataloguE entry's editors.
        """
        # Check and Return
        return self.editors.all().filter(id=user.id).exists()

    def lock(self) -> bool:
        """Locks the Catalogue Entry.

        Returns:
            bool: Whether the locking was successful.
        """
        # Check Catalogue Entry
        if self.is_unlocked():
            # Check if Catalogue Entry is new
            if self.is_new():
                # Lock the currently active layer
                self.active_layer.accept()

            # Calculate the attributes hash
            attributes_hash = utils.attributes_hash(self.attributes.all())

            # Compare attributes hash with current active layer submission
            if self.active_layer.hash == attributes_hash:
                # Set Catalogue Entry to Locked
                self.status = CatalogueEntryStatus.LOCKED

            else:
                # Set Catalogue Entry to Pending
                self.status = CatalogueEntryStatus.PENDING

            # Publish the Symbology
            self.symbology.publish()

            # Save the Catalogue Entry
            self.save()

            # Success!
            return True

        # Failed
        return False

    def unlock(self) -> bool:
        """Unlocks the Catalogue Entry.

        Returns:
            bool: Whether unlocking was successful.
        """
        # Check Catalogue Entry
        if self.is_locked() or self.is_pending():
            # Set Catalogue Entry to Draft
            self.status = CatalogueEntryStatus.DRAFT
            self.save()

            # Success!
            return True

        # Failed
        return False

    def decline(self) -> bool:
        """Declines the Catalogue Entry.

        Returns:
            bool: Whether the declining was successful.
        """
        # Check Catalogue Entry
        if self.is_unlocked():
            # Check if Catalogue Entry is new
            if self.is_new():
                # Decline the currently active layer
                self.active_layer.decline()

            # Set Catalogue Entry to Declined
            self.status = CatalogueEntryStatus.DECLINED
            self.save()

            # Success!
            return True

        # Failed
        return False

    def assign(self, user: auth_models.User) -> bool:
        """Assigns a user to the Catalogue Entry if applicable.

        Args:
            user (auth_models.User): User to be assigned.

        Returns:
            bool: Whether the assigning was successful.
        """
        # Check if the user can be assigned
        # To be assigned, a user must be:
        # 1. In the Catalogue Editors group
        # 2. One of this Catalogue Entry's editors
        if accounts_utils.is_catalogue_editor(user) and self.is_editor(user):
            # Assign user
            self.assigned_to = user
            self.save()

            # Success!
            return True

        # Failed
        return False

    def unassign(self) -> bool:
        """Unassigns the Catalogue Entry's user if applicable.

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
