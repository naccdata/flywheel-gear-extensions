"""Entry script for DBT Runner."""

import json
import logging
import re
from typing import Dict, Optional

from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.parameter_store import ParameterStore
from s3.s3_bucket import S3BucketInterface

from dbt_runner_app.main import run

log = logging.getLogger(__name__)

DIRECTORY_REGEX = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?$")


class DBTRunnerVisitor(GearExecutionEnvironment):
    """Visitor for the DBT Runner gear."""

    def __init__(
        self,
        client: ClientWrapper,
        dbt_project_zip: InputFileWrapper,
        source_prefixes: str,
        output_prefix: str,
        debug: bool = False,
    ):
        super().__init__(client=client)
        self.__dbt_project_zip = dbt_project_zip
        self.__source_prefixes = source_prefixes
        self.__output_prefix = output_prefix
        self.__debug = debug

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "DBTRunnerVisitor":
        """Creates a DBT Runner execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        dbt_project_zip = InputFileWrapper.create(
            input_name="dbt_project_zip", context=context
        )

        if not dbt_project_zip:
            raise GearExecutionError("DBT project zip required")

        source_prefixes = context.config.opts.get("source_prefixes", None)
        output_prefix = context.config.opts.get("output_prefix", None)

        if not source_prefixes:
            raise GearExecutionError("source_prefix required")
        if not output_prefix:
            raise GearExecutionError("output_prefix required")

        debug = context.config.opts.get("debug", False)

        if debug:
            log.setLevel(logging.DEBUG)
            log.info("Set logging level to DEBUG")

        return DBTRunnerVisitor(
            client=client,
            dbt_project_zip=dbt_project_zip,
            source_prefixes=source_prefixes,
            output_prefix=output_prefix,
            debug=debug,
        )

    def __load_source_prefixes(
        self, source_prefixes_str: str
    ) -> Dict[str, Dict[str, str]]:
        """Load and validate source prefixes. Also splits the source prefix
        into bucket and key and groups by bucket for easiser handling later.

        Args:
            source_prefixes_str: Source prefixes string to parse
        Returns:
            Validated table names and S3 keys, grouped by shared
            buckets
            {
                "bucket-1": {
                    "table1": "path/to/parquets"
                    "table2": "other-path-to-parquets"
                },
                "bucket2": {
                    "table3": "another/parquet/path"
                }
            }
        """
        source_prefixes = None
        try:
            source_prefixes = json.loads(source_prefixes_str)
        except json.decoder.JSONDecodeError as e:
            log.error(f"source_prefixes not a valid JSON string: {e}")

        if not source_prefixes:
            raise GearExecutionError("source_prefixes cannot be empty")

        results: Dict[str, Dict[str, str]] = {}
        table_names = set({})
        # make sure keys are valid
        for table, prefix in source_prefixes.items():
            # make sure key can be used as a directory name
            if not isinstance(table, str) or not DIRECTORY_REGEX.fullmatch(table):
                raise GearExecutionError(
                    f"'{table}' is not a valid key for directory name"
                )

            if table in table_names:
                raise GearExecutionError(f"Duplicate key: {table}")
            table_names.add(table)

            # make sure the value "looks like" a proper S3 prefix
            # and can be split into a bucket and key
            bucket, key = S3BucketInterface.parse_bucket_and_key(prefix)
            if bucket not in results:
                results[bucket] = {}

            results[bucket][table] = key

        log.info("Pulling from the following S3 locations:")
        log.info(json.dumps(results, indent=4))

        return results

    def run(self, context: GearContext) -> None:
        # load the source prefixes
        parsed_source_prefixes = self.__load_source_prefixes(self.__source_prefixes)

        run(
            context=context,
            dbt_project_zip=self.__dbt_project_zip,
            source_prefixes=parsed_source_prefixes,
            output_prefix=self.__output_prefix,
            dry_run=self.client.dry_run,
            debug=self.__debug,
        )


def main():
    """Main method for DBT Runner."""

    GearEngine.create_with_parameter_store().run(gear_type=DBTRunnerVisitor)


if __name__ == "__main__":
    main()
