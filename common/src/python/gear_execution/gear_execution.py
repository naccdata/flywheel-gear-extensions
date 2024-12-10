"""Module defining utilities for gear execution."""

import logging
import re
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, TypeVar

from centers.nacc_group import NACCGroup
from flywheel.client import Client
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from fw_client import FWClient
from inputs.parameter_store import ParameterError, ParameterStore

log = logging.getLogger(__name__)


class GearExecutionError(Exception):
    """Exception class for gear execution errors."""


class ClientWrapper:
    """Wrapper class for client objects."""

    def __init__(self, client: Client, dry_run: bool = False) -> None:
        self.__client = client
        self.__fw_client: Optional[FWClient] = None
        self.__dry_run = dry_run

    def get_proxy(self) -> FlywheelProxy:
        """Returns a proxy object for this client object."""
        return FlywheelProxy(client=self.__client,
                             fw_client=self.__fw_client,
                             dry_run=self.__dry_run)

    def set_fw_client(self, fw_client: FWClient) -> None:
        """Sets the FWClient needed by some proxy methods.

        Args:
          fw_client: the FWClient object
        """
        self.__fw_client = fw_client

    @property
    def host(self) -> str:
        """Returns the host for the client.

        Returns:
          hostname for the client.
        """
        api_client = self.__client.api_client  # type: ignore
        return api_client.configuration.host

    @property
    def dry_run(self) -> bool:
        """Returns whether client will run a dry run."""
        return self.__dry_run

    @property
    def client(self) -> Client:
        """Returns the Flywheel SDK client."""
        return self.__client


# pylint: disable=too-few-public-methods
class ContextClient:
    """Defines a factory method for creating a client wrapper for the gear
    context client."""

    @classmethod
    def create(cls, context: GearToolkitContext) -> ClientWrapper:
        """Creates a ContextClient object from the context object.

        Args:
          context: the gear context
        Returns:
          the constructed ContextClient
        Raises:
          GearExecutionError if the context does not have a client
        """
        if not context.client:
            raise GearExecutionError("Flywheel client required")

        return ClientWrapper(client=context.client,
                             dry_run=context.config.get("dry_run", False))


# pylint: disable=too-few-public-methods
class GearBotClient:
    """Defines a factory method for creating a client wrapper for a gear bot
    client."""

    @classmethod
    def create(cls, context: GearToolkitContext,
               parameter_store: Optional[ParameterStore]) -> ClientWrapper:
        """Creates a GearBotClient wrapper object from the context and
        parameter store.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Returns:
          the GearBotClient
        Raises:
          GearExecutionError if the context has no default client,
          the api key path is missing, or the host for the api key parameter
          does not match that of the default client.
        """
        try:
            default_client = ContextClient.create(context=context)
        except GearExecutionError as error:
            raise GearExecutionError(
                "Flywheel client required to confirm gearbot access"
            ) from error

        apikey_path_prefix = context.config.get("apikey_path_prefix", None)
        if not apikey_path_prefix:
            raise GearExecutionError("API key path prefix required")

        assert parameter_store, "Parameter store expected"
        try:
            api_key = parameter_store.get_api_key(
                path_prefix=apikey_path_prefix)
        except ParameterError as error:
            raise GearExecutionError(error) from error

        host = default_client.host
        if api_key.split(':')[0] not in host:
            raise GearExecutionError('Gearbot API key does not match host')

        return ClientWrapper(client=Client(api_key),
                             dry_run=default_client.dry_run)


class InputFileWrapper:
    """Defines a gear execution visitor that takes an input file."""

    def __init__(self, file_input: Dict[str, Dict[str, Any]]) -> None:
        self.file_input = file_input

    @property
    def file_id(self) -> str:
        """Returns the file ID."""
        return self.file_input['object']['file_id']

    @property
    def file_info(self) -> Dict[str, Any]:
        """Returns the file object info (metadata)."""
        return self.file_input['object']['info']

    @property
    def file_qc_info(self) -> Dict[str, Any]:
        """Returns the QC object in the file info."""
        return self.file_info.get('qc', {})

    @property
    def filename(self) -> str:
        """Returns the file name."""
        return self.file_input['location']['name']

    @property
    def filepath(self) -> str:
        """Returns the file path."""
        return self.file_input['location']['path']

    @property
    def file_type(self) -> str:
        """Returns the mimetype."""
        return self.file_input['object']['mimetype']

    @classmethod
    def create(cls, input_name: str,
               context: GearToolkitContext) -> Optional['InputFileWrapper']:
        """Creates the named InputFile.

        Will return None if the named input is optional and no file is given.

        Args:
          input_name: the name of the input file
          context: the gear context
        Returns:
          the input file object. None, if the input is optional and not given
        Raises:
          GearExecutionError if there is no input with the name
        """
        file_input = context.get_input(input_name)
        if not file_input:
            is_optional = context.manifest.get("inputs", {}).get(
                input_name, {}).get("optional", False)
            if is_optional:
                return None

            raise GearExecutionError(f'Missing input file {input_name}')

        if file_input["base"] != "file":
            raise GearExecutionError(
                f"The specified input {input_name} is not a file")
        if file_input["optional"] and not file_input['object']['file_id']:
            return None

        return InputFileWrapper(file_input=file_input)

    def get_validation_objects(self) -> List[Dict[str, Any]]:
        """Gets the QC validation objects from the file QC info."""
        result = []
        for gear_object in self.file_qc_info.values():
            validation_object = gear_object.get('validation', {})
            if validation_object:
                result.append(validation_object)
        return result

    def has_qc_errors(self) -> bool:
        """Check the QC validation objects in the file QC info for failures."""
        validation_objects = self.get_validation_objects()
        for validation_object in validation_objects:
            if validation_object['state'] == 'FAIL':
                return True
        return False

    def get_module_name_from_file_suffix(self) -> Optional[str]:
        """Get the module name from file suffix.

        Returns:
            str(optional): module name if a match found, else None
        """
        module = None
        pattern = '^.*-([a-z]+v[0-9])\\.(\\bcsv\\b|\\bjson\\b)$'
        if match := re.search(pattern, self.filename, re.IGNORECASE):
            module = match.group(1)

        return module


# pylint: disable=too-few-public-methods
class GearExecutionEnvironment(ABC):
    """Base class for gear execution environments."""

    def __init__(self, client: ClientWrapper) -> None:
        self.__client = client

    @property
    def client(self) -> ClientWrapper:
        """Returns the FW client for this environment."""
        return self.__client

    def admin_group(self, admin_id: str) -> NACCGroup:
        """Returns the admin group for this environment."""
        proxy = self.__client.get_proxy()
        try:
            return NACCGroup.create(proxy=proxy, group_id=admin_id)
        except FlywheelError as error:
            raise GearExecutionError(str(error)) from error

    @property
    def proxy(self) -> FlywheelProxy:
        """Returns the Flywheel proxy object for this environment."""
        return self.__client.get_proxy()

    @abstractmethod
    def run(self, context: GearToolkitContext) -> None:
        """Run the gear after initialization by visit methods.

        Note: expects both visit_context and visit_parameter_store to be called
        before this method.

        Args:
            context: The gear execution context
        """

    @classmethod
    def create(
        cls, context: GearToolkitContext,
        parameter_store: Optional[ParameterStore]
    ) -> 'GearExecutionEnvironment':
        """Creates an execution environment object from the context and
        parameter store.

        Implementing classes must implement the full signature.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Returns:
          the GearExecutionEnvironment initialized with the input
        """
        raise GearExecutionError("Not implemented")


# TODO: remove type ignore when using python 3.12 or above
E = TypeVar('E', bound=GearExecutionEnvironment)  # type: ignore


# pylint: disable=too-few-public-methods
class GearEngine:
    """Class defining the gear execution engine."""

    def __init__(self, parameter_store: Optional[ParameterStore] = None):
        self.parameter_store = parameter_store

    @classmethod
    def create_with_parameter_store(cls) -> 'GearEngine':
        """Creates a GearEngine with a parameter store defined from environment
        variables.

        Returns:
          GearEngine object with a parameter store
        Raises:
          GearExecutionError if there is an error getting the parameter
          store object.
        """
        try:
            parameter_store = ParameterStore.create_from_environment()
        except ParameterError as error:
            raise GearExecutionError(
                f'Unable to create Parameter Store: {error}') from error

        return GearEngine(parameter_store=parameter_store)

    def run(self, gear_type: Type[E]):
        """Execute the gear.

        Creates a execution environment object of the gear_type using the
        implementation of the GearExecutionEnvironment.create method.
        Then runs the gear.

        Args:
            gear_type: The type of the gear execution environment.
        """
        try:
            with GearToolkitContext() as context:
                context.init_logging()
                context.log_config()
                visitor = gear_type.create(
                    context=context, parameter_store=self.parameter_store)
                visitor.run(context)
        except GearExecutionError as error:
            log.error('Error: %s', error)
            sys.exit(1)
