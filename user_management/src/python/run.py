"""The run script for the user management gear."""

import logging
import sys

from admin.users import get_admin_users
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from inputs.arguments import build_parser_with_input
from inputs.context_parser import parse_config
from inputs.environment import get_api_key
from inputs.yaml import get_object_list
from user_main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    """Main method to manage users."""

    parser = build_parser_with_input()
    args = parser.parse_args()

    if args.gear:
        filename = 'user_file'
        with GearToolkitContext() as gear_context:
            gear_context.init_logging()
            context_args = parse_config(gear_context=gear_context,
                                        filename=filename)
            admin_group_name = context_args['admin_group']
            dry_run = context_args['dry_run']
            user_file = context_args[filename]
    else:
        dry_run = args.dry_run
        user_file = args.filename
        admin_group_name = args.admin_group

    user_list = get_object_list(user_file)
    if not user_list:
        sys.exit(1)

    api_key = get_api_key()
    if not api_key:
        log.error('No API key: expecting FW_API_KEY to be set')
        sys.exit(1)

    flywheel_proxy = FlywheelProxy(api_key=api_key, dry_run=dry_run)

    admin_users = get_admin_users(flywheel_proxy=flywheel_proxy,
                                  group_name=admin_group_name)

    run(proxy=flywheel_proxy, user_list=user_list, admin_users=admin_users)


if __name__ == "__main__":
    main()
