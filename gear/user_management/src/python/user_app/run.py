"""The run script for the user management gear."""

import logging
import sys
from io import StringIO
from typing import Any, List, Optional

from flywheel import Client
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from inputs.configuration import (ConfigurationError, get_group, get_project,
                                  read_file)
from inputs.context_parser import ConfigParseError
from inputs.parameter_store import ParameterError, ParameterStore
from inputs.yaml import YAMLReadError, get_object_lists_from_stream
from user_app.main import run

log = logging.getLogger(__name__)


def read_yaml_file(file_bytes: bytes) -> Optional[List[Any]]:
    """Reads user objects from YAML user file in the source project.

    Args:
      source: the project where user file is located
      user_filename: the name of the user file
    Returns:
      List of user objects
    """
    user_docs = get_object_lists_from_stream(
        StringIO(file_bytes.decode('utf-8')))
    if not user_docs or not user_docs[0]:
        return None

    return user_docs[0]


def main() -> None:
    """Main method to manage users."""

    with GearToolkitContext() as gear_context:
        gear_context.init_logging()

        try:
            parameter_store = ParameterStore.create_from_environment()
            api_key = parameter_store.get_api_key()
        except ParameterError as error:
            log.error('Parameter error: %s', error)
            sys.exit(1)

        dry_run = gear_context.config.get("dry_run", False)
        flywheel_proxy = FlywheelProxy(client=Client(api_key), dry_run=dry_run)
        try:
            admin_group = get_group(context=gear_context,
                                    proxy=flywheel_proxy,
                                    key='admin_group',
                                    default='nacc')
            source = get_project(context=gear_context,
                                 group=admin_group,
                                 project_key='source')
            file_bytes = read_file(context=gear_context,
                                   source=source,
                                   key='user_file')
            user_list = read_yaml_file(file_bytes)
        except ConfigurationError as error:
            log.error('Admin group not found: %s', error)
            sys.exit(1)
        except ConfigParseError as error:
            log.error('Cannot read directory file: %s', error.message)
            sys.exit(1)
        except YAMLReadError as error:
            log.error('No users read from user file: %s', error)
            sys.exit(1)

        admin_users = admin_group.get_group_users(access='admin')
        admin_set = {user.id for user in admin_users if user.id}

        run(proxy=flywheel_proxy, user_list=user_list, skip_list=admin_set)


if __name__ == "__main__":
    main()