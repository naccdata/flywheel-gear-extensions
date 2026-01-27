"""Main function for running template push process."""

import logging
import sys
from typing import List, Optional

from flywheel import Client
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from fw_gear import GearContext
from inputs.context_parser import ConfigParseError, get_config
from inputs.parameter_store import ParameterError, ParameterStore, S3Parameters
from projects.project_mapper import build_project_map
from s3.s3_bucket import S3BucketInterface

from metadata_app.main import run

log = logging.getLogger(__name__)


def main():
    """Main method to distribute metadata from S3 bucket to center projects."""

    with GearContext() as gear_context:
        gear_context.init_logging()
        gear_context.log_config()

        default_client = gear_context.client
        if not default_client:
            log.error("Flywheel client required to confirm gearbot access")
            sys.exit(1)

        try:
            s3_param_path: Optional[str] = get_config(
                gear_context=gear_context, key="s3_param_path"
            )
            destination_label: Optional[str] = get_config(
                gear_context=gear_context, key="destination_label"
            )
            table_list: List[str] = get_config(
                gear_context=gear_context, key="table_list"
            )
        except ConfigParseError as error:
            log.error("Incomplete configuration: %s", error.message)
            sys.exit(1)

        if not s3_param_path:
            log.error("Expected S3 parameter path")
            sys.exit(1)

        if not destination_label:
            log.error("Expected destination label")
            sys.exit(1)

        apikey_path_prefix = gear_context.config.opts.get(
            "apikey_path_prefix", "/prod/flywheel/gearbot"
        )
        log.info("Running gearbot with API key from %s/apikey", apikey_path_prefix)
        try:
            parameter_store = ParameterStore.create_from_environment()
            api_key = parameter_store.get_api_key(path_prefix=apikey_path_prefix)
            s3_parameters: S3Parameters = parameter_store.get_s3_parameters(
                param_path=s3_param_path
            )
        except ParameterError as error:
            log.error("Parameter error: %s", error)
            sys.exit(1)

        host = gear_context.client.api_client.configuration.host  # type: ignore
        if api_key.split(":")[0] not in host:
            log.error("Gearbot API key does not match host")
            sys.exit(1)

        dry_run = gear_context.config.opts.get("dry_run", False)
        proxy = FlywheelProxy(client=Client(api_key), dry_run=dry_run)

        project_map = build_project_map(
            proxy=proxy, destination_label=destination_label
        )
        if not project_map:
            log.error("No ADCID groups found")
            sys.exit(1)

        s3_client = S3BucketInterface.create_from(s3_parameters)
        if not s3_client:
            log.error("Unable to connect to S3")
            sys.exit(1)

        log.info(
            "Pulling metadata from S3 bucket %s into center %s projects",
            s3_client.bucket_name,
            destination_label,
        )
        if dry_run:
            log.info("Performing dry run")
        log.info("Including files %s", table_list)

        run(
            table_list=table_list,
            s3_client=s3_client,
            project_map=project_map,
            dry_run=dry_run,
        )


if __name__ == "__main__":
    main()
