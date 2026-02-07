"""The run script for the user management gear."""

import logging
from pathlib import Path
from typing import List, Optional

from botocore.exceptions import ClientError
from coreapi_client.api.default_api import DefaultApi
from coreapi_client.api_client import ApiClient
from coreapi_client.configuration import Configuration
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import (
    ParameterError,
    ParameterStore,
)
from inputs.yaml import YAMLReadError, load_from_stream
from notifications.email import EmailClient, create_ses_client
from pydantic import ValidationError
from redcap_api.redcap_repository import REDCapParametersRepository
from users.authorizations import AuthMap
from users.event_models import UserEventCollector
from users.event_notifications import UserEventNotificationGenerator
from users.user_entry import ActiveUserEntry, UserEntry
from users.user_process_environment import NotificationModeType
from users.user_processes import (
    NotificationClient,
    UserProcess,
    UserProcessEnvironment,
    UserQueue,
)
from users.user_registry import RegistryError, UserRegistry

from user_app.main import run

log = logging.getLogger(__name__)


class UserManagementVisitor(GearExecutionEnvironment):
    """Defines the user management gear."""

    def __init__(
        self,
        admin_id: str,
        client: ClientWrapper,
        user_filepath: Path,
        auth_filepath: Path,
        email_source: str,
        comanage_config: Configuration,
        comanage_coid: int,
        redcap_param_repo: REDCapParametersRepository,
        portal_url: str,
        notification_mode: NotificationModeType = "date",
        support_emails: Optional[List[str]] = None,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__user_filepath = user_filepath
        self.__auth_filepath = auth_filepath
        self.__email_source = email_source
        self.__comanage_config = comanage_config
        self.__comanage_coid = comanage_coid
        self.__redcap_param_repo = redcap_param_repo
        self.__notification_mode: NotificationModeType = notification_mode
        self.__portal_url = portal_url
        self.__support_emails = support_emails or []

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "UserManagementVisitor":
        """Visits the gear context to gather inputs.

        Args:
            context (GearContext): The gear context.
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        # Validate and retrieve file paths
        user_filepath, auth_filepath = cls._get_input_filepaths(context)

        # Retrieve required parameters from parameter store
        comanage_path = cls._require_config(
            context, "comanage_parameter_path", "CoManage parameter path"
        )
        notifications_path = cls._require_config(
            context, "notifications_path", "notifications parameter path"
        )
        portal_path = cls._require_config(
            context, "portal_url_path", "path for portal URL"
        )

        comanage_parameters = cls._get_parameters(
            parameter_store.get_comanage_parameters,
            comanage_path,
            "COManage configuration",
        )
        notification_params = cls._get_parameters(
            parameter_store.get_notification_parameters,
            notifications_path,
            "notification configuration",
        )
        portal_url = cls._get_parameters(
            parameter_store.get_portal_url, portal_path, "portal URL"
        )

        # Parse support emails from notification parameters
        support_emails = cls._parse_support_emails(
            notification_params["support_emails"]
        )

        # Create REDCap parameter repository
        redcap_param_repo = cls._create_redcap_repository(context, parameter_store)

        return UserManagementVisitor(
            admin_id=context.config.opts.get("admin_group", "nacc"),
            client=client,
            user_filepath=user_filepath,
            auth_filepath=auth_filepath,
            email_source=notification_params["sender"],
            comanage_coid=int(comanage_parameters["coid"]),
            comanage_config=Configuration(
                host=comanage_parameters["host"],
                username=comanage_parameters["username"],
                password=comanage_parameters["apikey"],
            ),
            redcap_param_repo=redcap_param_repo,
            notification_mode=context.config.opts.get("notification_mode", "none"),
            portal_url=portal_url["url"],
            support_emails=support_emails,
        )

    @staticmethod
    def _require_config(context: GearContext, key: str, description: str) -> str:
        """Get a required configuration value.

        Args:
            context: The gear context
            key: The configuration key
            description: Human-readable description for error messages

        Returns:
            The configuration value

        Raises:
            GearExecutionError: If the configuration value is missing
        """
        value = context.config.opts.get(key)
        if not value:
            raise GearExecutionError(f"No {description}")
        return value

    @staticmethod
    def _get_parameters(getter, path: str, description: str):
        """Get parameters from parameter store.

        Args:
            getter: The parameter store getter method
            path: The parameter path
            description: Human-readable description for error messages

        Returns:
            The parameters

        Raises:
            GearExecutionError: If parameter retrieval fails
        """
        try:
            return getter(path)
        except ParameterError as error:
            raise GearExecutionError(
                f"Parameter error - {description} required: {error}"
            ) from error

    @staticmethod
    def _get_input_filepaths(context: GearContext) -> tuple[Path, Path]:
        """Validate and retrieve input file paths from context.

        Args:
            context: The gear context

        Returns:
            Tuple of (user_filepath, auth_filepath)

        Raises:
            GearExecutionError: If required file paths are missing
        """
        user_filepath = context.config.get_input_path("user_file")
        if not user_filepath:
            raise GearExecutionError("No user directory file provided")

        auth_filepath = context.config.get_input_path("auth_file")
        if not auth_filepath:
            raise GearExecutionError("No user role file provided")

        return user_filepath, auth_filepath

    @staticmethod
    def _parse_support_emails(emails_str: str) -> list[str]:
        """Parse comma-separated email addresses.

        Args:
            emails_str: Comma-separated email addresses

        Returns:
            List of email addresses
        """
        if not emails_str:
            return []
        return [email.strip() for email in emails_str.split(",") if email.strip()]

    @staticmethod
    def _create_redcap_repository(
        context: GearContext, parameter_store: ParameterStore
    ) -> REDCapParametersRepository:
        """Create REDCap parameter repository from parameter store.

        Args:
            context: The gear context
            parameter_store: The parameter store instance

        Returns:
            REDCap parameter repository instance

        Raises:
            GearExecutionError: If repository creation fails
        """
        redcap_path = context.config.opts.get("redcap_parameter_path", "/redcap/aws")
        try:
            redcap_param_repo = REDCapParametersRepository.create_from_parameterstore(
                param_store=parameter_store, base_path=redcap_path
            )  # type: ignore
            if not redcap_param_repo:
                raise GearExecutionError("Failed to create REDCap parameter repository")
            return redcap_param_repo
        except (ParameterError, ValueError, TypeError) as error:
            raise GearExecutionError(
                f"Failed to create REDCap parameter repository: {error}"
            ) from error

    def run(self, context: GearContext) -> None:
        """Executes the gear.

        Args:
            context: the gear execution context
        """
        assert self.__user_filepath, "User directory file required"
        assert self.__auth_filepath, "User role file required"
        assert self.__admin_id, "Admin group ID required"
        assert self.__email_source, "Sender email address required"

        collector = UserEventCollector()
        with ApiClient(configuration=self.__comanage_config) as comanage_client:
            admin_group = self.admin_group(admin_id=self.__admin_id)
            admin_group.set_redcap_param_repo(self.__redcap_param_repo)

            try:
                run(
                    user_queue=self.__get_user_queue(self.__user_filepath),
                    user_process=UserProcess(
                        environment=UserProcessEnvironment(
                            admin_group=admin_group,
                            authorization_map=self.__get_auth_map(self.__auth_filepath),
                            notification_client=NotificationClient(
                                configuration_set_name="user-creation-claims",
                                email_client=EmailClient(
                                    client=create_ses_client(),
                                    source=self.__email_source,
                                ),
                                portal_url=self.__portal_url,
                                mode=self.__notification_mode,
                            ),
                            proxy=self.proxy,
                            registry=UserRegistry(
                                api_instance=DefaultApi(comanage_client),
                                coid=self.__comanage_coid,
                            ),
                        ),
                        collector=collector,
                    ),
                )
            except RegistryError as error:
                # Critical service failure - registry is essential for user management
                raise GearExecutionError(
                    f"Critical service failure - User registry error: {error}"
                ) from error

        if not collector.has_errors():
            log.info("User management completed successfully with no errors")
            return

        if not self.__support_emails:
            log.warning(
                "Errors occurred but no support emails configured. "
                "Skipping error notification."
            )
            return

        log.info(
            "Sending consolidated error notification for %d error(s)",
            collector.error_count(),
        )
        try:
            notification_generator = UserEventNotificationGenerator(
                email_client=EmailClient(
                    client=create_ses_client(),
                    source=self.__email_source,
                ),
                configuration_set_name="user-management-errors",
            )
            message_id = notification_generator.send_event_notification(
                collector=collector,
                gear_name="user_management",
                support_emails=self.__support_emails,
            )
            if message_id:
                log.info(
                    ("Successfully sent error notification with message ID: %s"),
                    message_id,
                )
            else:
                log.warning(
                    (
                        "Failed to send error notification - "
                        "notification system returned no message ID"
                    )
                )
        except (
            ClientError,
            ValidationError,
            ValueError,
        ) as notification_error:
            log.error(
                "Failed to send error notification email: %s. "
                "Individual errors have been logged. "
                "Gear run will continue.",
                notification_error,
                exc_info=True,
            )
            raise GearExecutionError(notification_error) from notification_error

    def __get_user_queue(self, user_file_path: Path) -> UserQueue[UserEntry]:
        """Get the active user objects from the user file.

        Args:
            user_file_path: The path to the user file.
        Returns:
            List of user objects
        """
        try:
            with open(user_file_path, "r", encoding="utf-8-sig") as user_file:
                object_list = load_from_stream(user_file)
        except YAMLReadError as error:
            raise GearExecutionError(
                f"No users read from user file {user_file_path}: {error}"
            ) from error
        if not object_list:
            raise GearExecutionError("No users found in user file")

        user_list: UserQueue[UserEntry] = UserQueue()
        for user_doc in object_list:
            try:
                if not user_doc.get("active"):
                    user_entry = UserEntry.model_validate(user_doc)
                else:
                    user_entry = ActiveUserEntry.model_validate(user_doc)
            except ValidationError as error:
                log.error("Error creating user entry: %s", error)
                continue

            if not user_entry.approved:
                log.warning("Skipping unapproved user with email %s", user_entry.email)
                continue

            user_list.enqueue(user_entry)

        return user_list

    def __get_auth_map(self, auth_file_path: Path) -> AuthMap:
        """Get the authorization map from the auth file.

        Args:
            auth_file_path: The path to the auth file.
        Returns:
            The authorization map
        """
        try:
            with open(auth_file_path, "r", encoding="utf-8-sig") as auth_file:
                auth_object = load_from_stream(auth_file)
                auth_map = AuthMap.model_validate(
                    auth_object,
                    context={"role_map": self.proxy.get_roles()},
                )
        except YAMLReadError as error:
            raise GearExecutionError(
                f"No authorizations read from auth file{auth_file_path}: {error}"
            ) from error
        except ValidationError as error:
            raise GearExecutionError(
                f"Unexpected format in auth file {auth_file_path}: {error}"
            ) from error
        except TypeError as error:
            raise GearExecutionError(
                f"Unexpected format in auth file {auth_file_path}: {error}"
            ) from error
        return auth_map


def main() -> None:
    """Main method to manage users."""

    GearEngine.create_with_parameter_store().run(gear_type=UserManagementVisitor)


if __name__ == "__main__":
    main()
