"""Main function for running template push process."""
import logging
import sys

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from inputs.arguments import build_base_parser
from inputs.context_parser import parse_config
from inputs.environment import get_api_key
from inputs.templates import get_template_projects
from push_template_main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def main():
    """Main method to copy template projects to center projects.

    Uses command line argument `gear` to indicate whether being run as a gear.
    If running as a gear, the arguments are taken from the gear context.
    Otherwise, arguments are taken from the command line.

    Arguments are
      * admin_group: the name of the admin group in the instance
        default is `nacc`
      * dry_run: whether to run as a dry run, default is False
      * the project file

    Gear rules are taken from template projects in the admin group.
    These projects are expected to be named `<datatype>-<stage>-template`,
    where `datatype` is one of the datatypes that occur in the project file,
    and `stage` is one of 'accepted', 'ingest' or 'retrospective'.
    (These are pipeline stages that can be created for the project)
    """
    parser = build_base_parser()
    args = parser.parse_args()

    if args.gear:
        with GearToolkitContext() as gear_context:
            gear_context.init_logging()
            context_args = parse_config(gear_context=gear_context,
                                        filename=None)
            admin_group_name = context_args['admin_group']
            dry_run = context_args['dry_run']
    else:
        dry_run = args.dry_run
        admin_group_name = args.admin_group

    api_key = get_api_key()
    if not api_key:
        log.error('No API key: expecting FW_API_KEY to be set')
        sys.exit(1)

    flywheel_proxy = FlywheelProxy(api_key=api_key, dry_run=dry_run)

    groups = flywheel_proxy.find_groups(admin_group_name)
    if not groups:
        log.warning("Admin group %s not found", admin_group_name)
        sys.exit(1)

    template_map = get_template_projects(group=groups[0], proxy=flywheel_proxy)
    run(proxy=flywheel_proxy,
        center_tag_pattern=r'adcid-\d+',
        template_map=template_map)


if __name__ == "__main__":
    main()
