"""Script to pull directory information and convert to file expected by the
user management gear."""
import logging
import sys

from directory_app.main import run
from flywheel_gear_toolkit import GearToolkitContext
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore
from redcap.redcap_connection import (REDCapConnectionError,
                                      REDCapReportConnection)
from yaml.representer import RepresenterError

log = logging.getLogger(__name__)


def main() -> None:
    """Main method for directory pull.

    Expects information needed for access to the user access report from
    the NACC directory on REDCap, and api key for flywheel. These must
    be given as environment variables.
    """

    with GearToolkitContext() as gear_context:
        gear_context.init_logging()

        try:
            parameter_store = ParameterStore.create_from_environment()
            param_path: str = get_config(gear_context=gear_context,
                                         key='parameter_path')
            report_parameters = parameter_store.get_redcap_report_connection(
                param_path=param_path)
            directory_proxy = REDCapReportConnection.create_from(
                report_parameters)
            user_report = directory_proxy.get_report_records()
        except ParameterError as error:
            log.error('Parameter error: %s', error)
            sys.exit(1)
        except ConfigParseError as error:
            log.error('Incomplete configuration: %s', error.message)
            sys.exit(1)
        except REDCapConnectionError as error:
            log.error('Failed to pull users from directory: %s', error.message)
            sys.exit(1)

        dry_run = gear_context.config.get("dry_run", False)
        try:
            user_filename: str = get_config(gear_context=gear_context,
                                            key='user_file')
        except ConfigParseError as error:
            log.error('Incomplete configuration: %s', error.message)
            sys.exit(1)

        try:
            yaml_text = run(user_report=user_report)
        except RepresenterError as error:
            log.error("Error: can't create YAML for file %s: %s",
                      user_filename, error)
            sys.exit(1)

        if dry_run:
            log.info('Would write user entries to file %s on %s %s',
                     user_filename, gear_context.destination['type'],
                     gear_context.destination['id'])
            return

        with gear_context.open_output(user_filename,
                                      mode='w',
                                      encoding='utf-8') as out_file:
            out_file.write(yaml_text)


if __name__ == "__main__":
    main()
