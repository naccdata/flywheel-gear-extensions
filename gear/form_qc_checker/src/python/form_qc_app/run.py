"""The entry point for the form-qc-check gear."""

import logging
import sys

from flywheel import Client
from flywheel_gear_toolkit import GearToolkitContext
from form_qc_app.main import run
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore
from redcap.redcap_connection import REDCapReportConnection
from s3.s3_client import S3BucketReader

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def main():
    """Load necessary environment variables, create Flywheel, S3 connections,
    invoke QC app."""

    with GearToolkitContext() as gear_context:
        gear_context.init_logging()
        gear_context.log_config()

        default_client = gear_context.client
        if not default_client:
            log.error('Flywheel client required to confirm gearbot access')
            sys.exit(1)

        apikey_path_prefix = gear_context.config.get("apikey_path_prefix",
                                                     "/prod/flywheel/gearbot")
        log.info('Running gearbot with API key from %s/apikey',
                 apikey_path_prefix)

        try:
            parameter_store = ParameterStore.create_from_environment()
            api_key = parameter_store.get_api_key(
                path_prefix=apikey_path_prefix)

            s3_param_path = get_config(gear_context=gear_context,
                                       key='parameter_path')
            s3_parameters = parameter_store.get_s3_parameters(
                param_path=s3_param_path)

            qc_checks_db_path = gear_context.config.get(
                'qc_checks_db_path', '/redcap/aws/qcchecks')
            redcap_params = parameter_store.get_redcap_report_connection(
                param_path=qc_checks_db_path)
        except ParameterError as error:
            log.error('Parameter error: %s', error)
            sys.exit(1)
        except ConfigParseError as error:
            log.error('Incomplete configuration: %s', error.message)
            sys.exit(1)

        host = gear_context.client.api_client.configuration.host  # type: ignore
        if api_key.split(':')[0] not in host:
            log.error('Gearbot API key does not match host')
            sys.exit(1)

        fw_client = Client(api_key)

        s3_client = S3BucketReader.create_from(s3_parameters)
        if not s3_client:
            log.error('Unable to connect to S3')
            sys.exit(1)

        redcap_connection = REDCapReportConnection.create_from(redcap_params)

        run(fw_client=fw_client,
            s3_client=s3_client,
            gear_context=gear_context,
            redcap_connection=redcap_connection)


if __name__ == "__main__":
    main()
