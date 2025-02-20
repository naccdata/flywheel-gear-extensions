"""The run script for the user management gear."""

import logging
from typing import Optional

from coreapi_client.api.default_api import DefaultApi
from coreapi_client.api_client import ApiClient
from coreapi_client.configuration import Configuration
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterError, ParameterStore
from inputs.yaml import YAMLReadError, load_from_stream
from notifications.email import EmailClient, create_ses_client
from pydantic import ValidationError
from redcap_api.redcap_repository import REDCapParametersRepository
from users.authorizations import AuthMap
from users.nacc_directory import UserEntry, UserFormatError
from users.user_processes import (
    NotificationClient,
    NotificationModeType,
    UserProcess,
    UserProcessEnvironment,
    UserQueue,
)
from users.user_registry import RegistryError, UserRegistry

from user_app.main import run

log = logging.getLogger(__name__)


class UserManagementVisitor(GearExecutionEnvironment):
    """Defines the user management gear."""

    def __init__(self,
                 admin_id: str,
                 client: ClientWrapper,
                 user_filepath: str,
                 auth_filepath: str,
                 email_source: str,
                 comanage_config: Configuration,
                 comanage_coid: int,
                 redcap_param_repo: REDCapParametersRepository,
                 portal_url: str,
                 notification_mode: NotificationModeType = 'date'):
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

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'UserManagementVisitor':
        """Visits the gear context to gather inputs.

        Args:
            context (GearToolkitContext): The gear context.
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        user_filepath = context.get_input_path('user_file')
        if not user_filepath:
            raise GearExecutionError('No user directory file provided')
        auth_filepath = context.get_input_path('auth_file')
        if not auth_filepath:
            raise GearExecutionError('No user role file provided')

        comanage_path = context.config.get('comanage_parameter_path')
        if not comanage_path:
            raise GearExecutionError("No CoManage parameter path")
        sender_path = context.config.get('sender_path')
        if not sender_path:
            raise GearExecutionError('No email sender parameter path')

        portal_path = context.config.get('portal_url_path')
        if not portal_path:
            raise GearExecutionError("No path for portal URL")

        try:
            comanage_parameters = parameter_store.get_comanage_parameters(
                comanage_path)
            sender_parameters = parameter_store.get_notification_parameters(
                sender_path)
            portal_url = parameter_store.get_portal_url(portal_path)
        except ParameterError as error:
            raise GearExecutionError(f'Parameter error: {error}') from error

        redcap_path = context.config.get("redcap_parameter_path",
                                         "/redcap/aws")
        redcap_param_repo = REDCapParametersRepository.create_from_parameterstore(
            param_store=parameter_store, base_path=redcap_path)  # type: ignore
        if not redcap_param_repo:
            raise GearExecutionError(
                'Failed to create REDCap parameter repository')

        return UserManagementVisitor(
            admin_id=context.config.get("admin_group", "nacc"),
            client=client,
            user_filepath=user_filepath,
            auth_filepath=auth_filepath,
            email_source=sender_parameters['sender'],
            comanage_coid=int(comanage_parameters['coid']),
            comanage_config=Configuration(
                host=comanage_parameters['host'],
                username=comanage_parameters['username'],
                password=comanage_parameters['apikey']),
            redcap_param_repo=redcap_param_repo,
            notification_mode=context.config.get('notification_mode', 'none'),
            portal_url=portal_url['url'])

    def run(self, context: GearToolkitContext) -> None:
        """Executes the gear.

        Args:
            context: the gear execution context
        """
        assert self.__user_filepath, 'User directory file required'
        assert self.__auth_filepath, 'User role file required'
        assert self.__admin_id, 'Admin group ID required'
        assert self.__email_source, 'Sender email address required'

        with ApiClient(
                configuration=self.__comanage_config) as comanage_client:
            admin_group = self.admin_group(admin_id=self.__admin_id)
            admin_group.set_redcap_param_repo(self.__redcap_param_repo)

            try:
                run(
                    user_queue=self.__get_user_queue(self.__user_filepath),
                    user_process=UserProcess(
                        environment=UserProcessEnvironment(
                            admin_group=admin_group,
                            authorization_map=self.__get_auth_map(
                                self.__auth_filepath),
                            notification_client=NotificationClient(
                                configuration_set_name="user-creation-claims",
                                email_client=EmailClient(
                                    client=create_ses_client(),
                                    source=self.__email_source),
                                portal_url=self.__portal_url,
                                mode=self.__notification_mode),
                            proxy=self.proxy,
                            registry=UserRegistry(api_instance=DefaultApi(
                                comanage_client),
                                                  coid=self.__comanage_coid))),
                )
            except RegistryError as error:
                raise GearExecutionError(
                    f'User registry error: {error}') from error

    def __get_user_queue(self, user_file_path: str) -> UserQueue[UserEntry]:
        """Get the active user objects from the user file.

        Args:
            user_file_path: The path to the user file.
        Returns:
            List of user objects
        """
        try:
            with open(user_file_path, 'r', encoding='utf-8') as user_file:
                object_list = load_from_stream(user_file)
        except YAMLReadError as error:
            raise GearExecutionError(
                f'No users read from user file {user_file_path}: {error}'
            ) from error
        if not object_list:
            raise GearExecutionError('No users found in user file')

        user_list: UserQueue[UserEntry] = UserQueue()
        for user_doc in object_list:
            try:
                user_entry = UserEntry.create(user_doc)
            except UserFormatError as error:
                log.error('Error creating user entry: %s', error)
                continue

            user_list.enqueue(user_entry)

        return user_list

    def __get_auth_map(self, auth_file_path: str) -> AuthMap:
        """Get the authorization map from the auth file.

        Args:
            auth_file_path: The path to the auth file.
        Returns:
            The authorization map
        """
        try:
            with open(auth_file_path, 'r', encoding='utf-8') as auth_file:
                auth_object = load_from_stream(auth_file)
                auth_map = AuthMap(project_authorizations=auth_object)
        except YAMLReadError as error:
            raise GearExecutionError('No authorizations read from auth file'
                                     f'{auth_file_path}: {error}') from error
        except ValidationError as error:
            raise GearExecutionError(
                f'Unexpected format in auth file {auth_file_path}: {error}'
            ) from error
        return auth_map


def main() -> None:
    """Main method to manage users."""

    GearEngine.create_with_parameter_store().run(
        gear_type=UserManagementVisitor)


if __name__ == "__main__":
    main()
