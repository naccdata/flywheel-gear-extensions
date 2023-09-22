"""The run script for the user management gear."""

import logging
import sys

from admin.users import get_admin_users
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from inputs.api_key import get_api_key
from inputs.context_parser import parse_config
from inputs.yaml import get_object_list
from user_app.main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    """Main method to manage users."""

    filename = 'user_file'
    with GearToolkitContext() as gear_context:
        gear_context.init_logging()
        context_args = parse_config(gear_context=gear_context,
                                    filename=filename)
        admin_group_name = context_args['admin_group']
        dry_run = context_args['dry_run']
        user_file = context_args[filename]
        api_key = gear_context.get_input('api-key')

    if not api_key:
        api_key = get_api_key()

    user_list = get_object_list(user_file)
    if not user_list:
        sys.exit(1)

    if not api_key:
        log.error('No API key found. Cannot connect to Flywheel')
        sys.exit(1)

    flywheel_proxy = FlywheelProxy(api_key=api_key, dry_run=dry_run)

    admin_users = get_admin_users(flywheel_proxy=flywheel_proxy,
                                  group_name=admin_group_name)

    run(proxy=flywheel_proxy, user_list=user_list, admin_users=admin_users)


if __name__ == "__main__":
    main()
