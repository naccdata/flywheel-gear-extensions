"""The entry point for the form-qc-check gear."""

import logging
import sys

from flywheel import Client
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from form_qc_app.main import run
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore
from s3.s3_client import S3BucketReader

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


def main():
    """Load necessary environment variables, create Flywheel, S3 connections,
    invoke QC app."""

    with GearToolkitContext() as gear_context:
        gear_context.init_logging()
        gear_context.log_config()

        try:
            parameter_store = ParameterStore.create_from_environment()
            api_key = parameter_store.get_api_key()

            s3_param_path = get_config(gear_context=gear_context,
                                       key='parameter_path')
            s3_parameters = parameter_store.get_s3_parameters(
                param_path=s3_param_path)
        except ParameterError as error:
            log.error('Parameter error: %s', error)
            sys.exit(1)
        except ConfigParseError as error:
            log.error('Incomplete configuration: %s', error.message)
            sys.exit(1)

        dry_run = gear_context.config.get("dry_run", False)
        fw_client = Client(api_key)
        proxy = FlywheelProxy(client=fw_client, dry_run=dry_run)

        s3_client = S3BucketReader.create_from(s3_parameters)
        if not s3_client:
            log.error('Unable to connect to S3')
            sys.exit(1)

    run(fw_client=fw_client,
        proxy=proxy,
        s3_client=s3_client,
        gear_context=gear_context)


if __name__ == "__main__":
    main()
