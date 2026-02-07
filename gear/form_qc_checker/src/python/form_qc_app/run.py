"""The entry point for the form-qc-check gear."""

import logging
import sys
from typing import Optional

from configs.ingest_configs import load_form_ingest_configurations
from flywheel_gear_toolkit import GearToolkitContext
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    InputFileWrapper,
)
from inputs.context_parser import get_config
from inputs.parameter_store import ParameterError, ParameterStore
from keys.keys import DefaultValues
from pydantic import ValidationError
from redcap_api.redcap_connection import (
    REDCapConnectionError,
    REDCapReportConnection,
)
from s3.s3_bucket import S3BucketInterface

from form_qc_app.main import run

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)


class FormQCCheckerVisitor(GearExecutionEnvironment):
    """The gear execution visitor for the form-qc-checker app."""

    def __init__(
        self,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        config_input: InputFileWrapper,
        redcap_con: REDCapReportConnection,
        s3_client: S3BucketInterface,
        supplement_input: Optional[InputFileWrapper] = None,
    ):
        """
        Args:
            client: Flywheel SDK client wrapper
            file_input: Gear input file wrapper
            config_input: forms module configurations file
            redcap_con: REDCap project for NACC QC checks
            s3_client: boto3 client for QC rules S3 bucket
            supplement_input: supplement input file (e.g. UDS for FTLD/LBD validations)
        """
        super().__init__(client=client)
        self.__file_input = file_input
        self.__config_input = config_input
        self.__redcap_con = redcap_con
        self.__s3_client = s3_client
        self.__supplement_input = supplement_input

    @classmethod
    def create(
        cls, context: GearContext, parameter_store: Optional[ParameterStore]
    ) -> "FormQCCheckerVisitor":
        """Creates a form-qc-checker execution visitor.

        Args:
          context: the gear context
          parameter_store: the parameter store
        Raises:
          GearExecutionError if any error occurred while parsing gear configs
        """
        assert parameter_store, "Parameter store expected"

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(
            input_name="form_data_file", context=context
        )
        assert file_input, "missing expected input, form_data_file"

        form_configs_input = InputFileWrapper.create(
            input_name="form_configs_file", context=context
        )
        assert form_configs_input, "missing expected input, form_configs_file"

        supplement_input = InputFileWrapper.create(
            input_name="supplement_data_file", context=context
        )

        rules_s3_bucket: str = get_config(
            gear_context=context, key="rules_s3_bucket", default="nacc-qc-rules"
        )
        qc_checks_db_path: str = get_config(
            gear_context=context,
            key="qc_checks_db_path",
            default="/redcap/aws/qcchecks",
        )

        try:
            redcap_params = parameter_store.get_redcap_report_parameters(
                param_path=qc_checks_db_path
            )
        except ParameterError as error:
            raise GearExecutionError(f"Parameter error: {error}") from error

        s3_client = S3BucketInterface.create_from_environment(rules_s3_bucket)
        if not s3_client:
            raise GearExecutionError(f"Unable to access S3 bucket {rules_s3_bucket}")

        try:
            redcap_con = REDCapReportConnection.create_from(redcap_params)
        except REDCapConnectionError as error:
            raise GearExecutionError(error) from error

        return FormQCCheckerVisitor(
            client=client,
            file_input=file_input,
            config_input=form_configs_input,
            redcap_con=redcap_con,
            s3_client=s3_client,
            supplement_input=supplement_input,
        )

    def run(self, context: GearContext):
        """Runs the form-qc-checker app.

        Args:
            context: the gear execution context
        """

        assert context, "Gear context required"

        admin_group = self.admin_group(
            admin_id=context.config.opts.get("admin_group", DefaultValues.NACC_GROUP_ID)
        )

        try:
            form_project_configs = load_form_ingest_configurations(
                self.__config_input.filepath
            )
        except ValidationError as error:
            raise GearExecutionError(
                "Error reading form configurations file"
                f"{self.__config_input.filename}: {error}"
            ) from error

        run(
            gear_name=self.gear_name(context, "form-qc-checker"),
            client_wrapper=self.client,
            input_wrapper=self.__file_input,
            s3_client=self.__s3_client,
            admin_group=admin_group,
            gear_context=context,
            form_project_configs=form_project_configs,
            redcap_connection=self.__redcap_con,
            supplement_input=self.__supplement_input,
        )


def main():
    """Load necessary environment variables, create Flywheel, S3 connections,
    invoke QC app."""

    GearEngine.create_with_parameter_store().run(gear_type=FormQCCheckerVisitor)


if __name__ == "__main__":
    main()
