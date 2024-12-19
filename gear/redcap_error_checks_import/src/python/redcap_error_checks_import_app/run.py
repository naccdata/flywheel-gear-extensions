"""Entry script for REDCap Import Error Checks."""
import logging
from typing import List, Optional

from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.context_parser import get_config
from inputs.parameter_store import ParameterError, ParameterStore
from redcap.redcap_connection import REDCapConnection, REDCapConnectionError
from redcap.redcap_project import REDCapProject
from s3.s3_client import S3BucketReader

from redcap_error_checks_import_app.main import run

log = logging.getLogger(__name__)


class REDCapImportErrorChecksVisitor(GearExecutionEnvironment):
    """Visitor for the REDCap Import Error Checks gear."""

    def __init__(self,
                 client: ClientWrapper,
                 s3_bucket: S3BucketReader,
                 redcap_project: REDCapProject,
                 modules: List[str],
                 fail_fast: bool = True):
        """Initializer."""
        super().__init__(client=client)

        self.__s3_bucket = s3_bucket
        self.__redcap_project = redcap_project
        self.__modules = modules
        self.__fail_fast = fail_fast

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'REDCapImportErrorChecksVisitor':
        """Creates a gear execution object.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """
        client = GearBotClient.create(context=context,
                                      parameter_store=parameter_store)

        checks_s3_bucket: str = get_config(gear_context=context,
                                           key='checks_s3_bucket',
                                           default='nacc-qc-rules')
        qc_checks_db_path: str = get_config(gear_context=context,
                                            key='qc_checks_db_path',
                                            default='/redcap/aws/qcchecks')
        fail_fast: bool = get_config(gear_context=context,
                                     key='fail_fast',
                                     default=True)
        modules: List[str] = get_config(gear_context=context,
                                        key='modules',
                                        default='all').split(',')

        try:
            redcap_params = parameter_store.get_redcap_report_parameters(  # type: ignore
                param_path=qc_checks_db_path)
        except ParameterError as error:
            raise GearExecutionError(
                f'REDCap parameter error: {error}') from error

        s3_bucket = S3BucketReader.create_from_environment(checks_s3_bucket)
        if not s3_bucket:
            raise GearExecutionError(
                f'Unable to access S3 bucket {checks_s3_bucket}')

        try:
            redcap_connection = REDCapConnection.create_from(redcap_params)
            redcap_project = REDCapProject.create(redcap_connection)
        except REDCapConnectionError as error:
            raise GearExecutionError(error) from error

        return REDCapImportErrorChecksVisitor(client=client,
                                              redcap_project=redcap_project,
                                              s3_bucket=s3_bucket,
                                              modules=modules,
                                              fail_fast=fail_fast)

    def run(self, context: GearToolkitContext) -> None:
        run(proxy=self.proxy,
            s3_bucket=self.__s3_bucket,
            redcap_project=self.__redcap_project,
            modules=self.__modules,
            fail_fast=self.__fail_fast)


def main():
    """Main method for REDCap Import Error Checks."""

    GearEngine().create_with_parameter_store().\
        run(gear_type=REDCapImportErrorChecksVisitor)


if __name__ == "__main__":
    main()
