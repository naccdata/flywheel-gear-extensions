"""User process environment for user management operations."""

from datetime import datetime
from typing import Literal, Optional

from centers.nacc_group import NACCGroup
from flywheel import User
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from notifications.email import (
    DestinationModel,
    EmailClient,
    TemplateDataModel,
)

from users.authorizations import AuthMap
from users.user_entry import ActiveUserEntry
from users.user_registry import RegistryPerson, UserRegistry

NotificationModeType = Literal["date", "force", "none"]


class NotificationClient:
    """Wrapper for the email client to send email notifications for the user
    enrollment flow."""

    def __init__(
        self,
        email_client: EmailClient,
        configuration_set_name: str,
        portal_url: str,
        mode: NotificationModeType,
    ) -> None:
        self.__client = email_client
        self.__configuration_set_name = configuration_set_name
        self.__portal_url = portal_url
        self.__mode: NotificationModeType = mode

    def __claim_template(self, user_entry: ActiveUserEntry) -> TemplateDataModel:
        """Creates the email data template from the user entry for a registry
        claim email.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry
        Returns:
          the template model with first name and auth email address
        """
        assert user_entry.auth_email, "user entry must have auth email"
        return TemplateDataModel(
            firstname=user_entry.first_name, email_address=user_entry.auth_email
        )

    def __claim_destination(self, user_entry: ActiveUserEntry) -> DestinationModel:
        """Creates the email destination from the user entry for a registry
        claim email.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry
        Returns:
          the destination model with auth email address.
        """
        assert user_entry.auth_email, "user entry must have auth email"
        return DestinationModel(to_addresses=[user_entry.auth_email])

    def send_claim_email(self, user_entry: ActiveUserEntry) -> None:
        """Sends the initial claim email to the auth email of the user.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry for the user
        """
        self.__client.send(
            configuration_set_name=self.__configuration_set_name,
            destination=self.__claim_destination(user_entry),
            template="claim",
            template_data=self.__claim_template(user_entry),
        )

    def send_followup_claim_email(self, user_entry: ActiveUserEntry) -> None:
        """Sends the followup claim email to the auth email of the user.

        The user entry must have the auth email address set.

        Args:
          user_entry: the user entry for the user
        """
        if self.__should_send(user_entry):
            self.__client.send(
                configuration_set_name=self.__configuration_set_name,
                destination=self.__claim_destination(user_entry),
                template="followup-claim",
                template_data=self.__claim_template(user_entry),
            )

    def send_creation_email(self, user_entry: ActiveUserEntry) -> None:
        """Sends the user creation email to the email of the user.

        Args:
          user_entry: the user entry for the user
        """
        assert user_entry.auth_email, "user entry must have auth email"
        self.__client.send(
            configuration_set_name=self.__configuration_set_name,
            destination=DestinationModel(
                to_addresses=[user_entry.email], cc_addresses=[user_entry.auth_email]
            ),
            template="user-creation",
            template_data=TemplateDataModel(
                firstname=user_entry.first_name, url=self.__portal_url
            ),
        )

    def __should_send(self, user_entry: ActiveUserEntry) -> bool:
        """Determines whether to send a notification.

        If notification mode is force, then returns true.
        If mode is none, returns False.
        If mode is date, returns true if the number of days since creation is
        a multiple of 7, and False otherwise.

        Args:
        user_entry: the directory entry for user
        Returns:
        True if criteria for notification mode is met. False, otherwise.
        """
        if self.__mode == "force":
            return True
        if self.__mode == "none":
            return False

        assert user_entry.registration_date, "user must be registered"

        time_since_creation = user_entry.registration_date - datetime.now()
        return time_since_creation.days % 7 == 0 and time_since_creation.days / 7 <= 3


class UserProcessEnvironment:
    """Defines the environment consisting of services used in user
    management."""

    def __init__(
        self,
        *,
        admin_group: NACCGroup,
        authorization_map: AuthMap,
        proxy: FlywheelProxy,
        registry: UserRegistry,
        notification_client: NotificationClient,
    ) -> None:
        self.__admin_group = admin_group
        self.__authorization_map = authorization_map
        self.__proxy = proxy
        self.__registry = registry
        self.__notification_client = notification_client

    @property
    def admin_group(self) -> NACCGroup:
        return self.__admin_group

    @property
    def authorization_map(self) -> AuthMap:
        return self.__authorization_map

    @property
    def proxy(self) -> FlywheelProxy:
        return self.__proxy

    @property
    def user_registry(self) -> UserRegistry:
        return self.__registry

    @property
    def notification_client(self) -> NotificationClient:
        return self.__notification_client

    def add_user(self, user: User) -> str:
        return self.proxy.add_user(user)

    def find_user(self, user_id: str) -> Optional[User]:
        return self.proxy.find_user(user_id)

    def get_from_registry(self, email: str) -> list[RegistryPerson]:
        return self.user_registry.get(email=email)
