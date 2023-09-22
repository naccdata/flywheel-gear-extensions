"""Script to pull directory information and convert to file expected by the
user management gear."""
import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

import flywheel
import yaml
from flywheel import FileSpec
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from inputs.api_key import get_api_key
from inputs.arguments import build_parser_with_output
from inputs.context_parser import parse_config
from inputs.environment import get_environment_variable
from redcap.nacc_directory import UserDirectoryEntry
from redcap.redcap_connection import REDCapConnection, REDCapConnectionError

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


# pylint: disable=(too-many-locals)
def main() -> None:
    """Main method for directory pull.

    Expects information needed for access to the user access report from
    the NACC directory on REDCap, and api key for flywheel. These must
    be given as environment variables.
    """

    parser = build_parser()
    args = parser.parse_args()

    if args.gear:
        filename = 'user_file'
        with GearToolkitContext() as gear_context:
            gear_context.init_logging()
            context_args = parse_config(gear_context=gear_context,
                                        filename=filename)
            admin_group_name = context_args['admin_group']
            dry_run = context_args['dry_run']
            user_filename = context_args[filename]
            api_key = gear_context.get_input('api-key')
    else:
        dry_run = args.dry_run
        user_filename = args.filename
        admin_group_name = args.admin_group
        api_key = get_api_key()

    if not api_key:
        log.error('No API key found. Cannot connect to Flywheel')
        sys.exit(1)

    url_variable = 'NACC_DIRECTORY_URL'
    directory_url = get_environment_variable(url_variable)
    if not directory_url:
        log.error('No URL: expecting %s to be set', url_variable)
        sys.exit(1)

    token_variable = 'NACC_DIRECTORY_TOKEN'
    directory_token = get_environment_variable(token_variable)
    if not directory_token:
        log.error('No project token: expecting %s to be set', token_variable)
        sys.exit(1)

    report_id_variable = 'USER_REPORT_ID'
    user_report_id = get_environment_variable(report_id_variable)
    if not user_report_id:
        log.error('No report ID: expecting %s to be set', report_id_variable)
        sys.exit(1)

    user_entries = []
    try:
        user_entries = get_user_records(directory_token=directory_token,
                                        directory_url=directory_url,
                                        user_report_id=user_report_id)
    except REDCapConnectionError as error:
        log.error('Failed to pull users from directory: %s', error.error)
        sys.exit(1)

    if args.gear or args.upload:
        admin_project = get_admin_project(admin_group_name, dry_run, api_key)
        if not admin_project:
            log.error('No admin group %s, cannot upload file %s',
                      admin_group_name, user_filename)
            sys.exit(1)

        if dry_run:
            log.info('Would write user entries to file %s on project %s',
                     user_filename, admin_project.label)
            return

        admin_project.upload_file(
            FileSpec(user_filename,
                     contents=yaml.safe_dump(user_entries),
                     content_type='text/yaml'))
    else:
        with open(user_filename, mode='w', encoding='utf-8') as user_file:
            yaml.safe_dump(user_entries, user_file)


def get_admin_project(admin_group_name: str, dry_run: bool,
                      api_key: str) -> Optional[flywheel.Project]:
    """Gets the admin project from the admin group.

    Args:
      admin_group_name: the name of the admin group
      dry_run: whether to do a dry run on FW operations
      api_key: the FW API key
    """
    flywheel_proxy = FlywheelProxy(api_key=api_key, dry_run=dry_run)
    admin_group = None
    groups = flywheel_proxy.find_groups(admin_group_name)
    if groups:
        admin_group = groups[0]
    else:
        log.error("Admin group %s not found", admin_group_name)
        return None

    project_name = 'project-admin'
    admin_project = flywheel_proxy.get_project(group=admin_group,
                                               project_label=project_name)
    if not admin_project:
        log.error('Unable to access admin project: %s', project_name)
        return None

    return admin_project


def get_user_records(*, directory_token: str, directory_url: str,
                     user_report_id: str) -> List[Dict[str, Any]]:
    """Convert records in directory user report to UserDirectoryEntry and save
    as list of dictionary objects.

    Args:
      user_report: the list of user records from directory report
    """

    directory_proxy = REDCapConnection(token=directory_token,
                                       url=directory_url)

    user_report = directory_proxy.request_json_value(
        data={
            'content': 'report',
            'report_id': str(user_report_id),
            'csvDelimiter': '',
            'rawOrLabel': 'raw',
            'rawOrLabelHeaders': 'raw',
            'exportCheckboxLabel': 'false'
        },
        message="pulling user report from NACC Directory")

    user_entries = []
    for user_record in user_report:
        entry = UserDirectoryEntry.create_from_record(user_record)
        if entry:
            user_entries.append(entry.as_dict())
    return user_entries


def build_parser() -> argparse.ArgumentParser:
    """Creates an argument parser customized to pulling from directory."""
    parser = build_parser_with_output()
    parser.add_argument('-u',
                        '--upload',
                        help='whether to upload to file to admin group',
                        default=False,
                        action='store_true')
    return parser


if __name__ == "__main__":
    main()
