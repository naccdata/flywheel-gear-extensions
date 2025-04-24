"""Entry script for Regression Curator."""
import logging
from typing import List, Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel import FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
    get_project_from_destination,
)
from inputs.parameter_store import ParameterStore
from outputs.errors import FileError, MPListErrorWriter
from outputs.outputs import write_csv_to_stream
from utils.utils import parse_string_to_list

from regression_curator_app.main import run

log = logging.getLogger(__name__)


class RegressionCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the Regression Curator gear."""

    def __init__(self, client: ClientWrapper, project: ProjectAdaptor,
                 s3_qaf_file: str, keep_fields: List[str],
                 filename_pattern: str, error_outfile: str):
        super().__init__(client=client)
        self.__project = project
        self.__s3_qaf_file = s3_qaf_file
        self.__keep_fields = keep_fields
        self.__filename_pattern = filename_pattern
        self.__error_outfile = error_outfile

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None
    ) -> 'RegressionCuratorVisitor':
        """Creates a Regression Curator execution visitor.

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

        s3_qaf_file = context.config.get("s3_qaf_file", None)
        if not s3_qaf_file:
            raise GearExecutionError("s3_qaf_file required")

        keep_fields = parse_string_to_list(
            context.config.get('keep_fields', ''))
        filename_pattern = context.config.get('filename_pattern', "*UDS.json")

        proxy = client.get_proxy()
        fw_project = get_project_from_destination(context=context, proxy=proxy)
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        error_outfile = context.config.get("error_outfile",
                                           'regression_errors.csv')

        return RegressionCuratorVisitor(client=client,
                                        project=project,
                                        s3_qaf_file=s3_qaf_file,
                                        keep_fields=keep_fields,
                                        filename_pattern=filename_pattern,
                                        error_outfile=error_outfile)

    def run(self, context: GearToolkitContext) -> None:
        try:
            fw_path = self.proxy.get_lookup_path(self.__project.project)
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to find the input file: {error}') from error

        error_writer = MPListErrorWriter(container_id=self.__project.id,
                                         fw_path=fw_path)

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                filename_pattern=self.__filename_pattern)
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(context=context,
            s3_qaf_file=self.__s3_qaf_file,
            keep_fields=self.__keep_fields,
            scheduler=scheduler,
            error_writer=error_writer)

        errors = list(error_writer.errors())

        if errors:
            log.error(
                f"Errors detected, writing errors to output file {self.__error_outfile}"
            )
            contents = write_csv_to_stream(headers=FileError.fieldnames(),
                                           data=errors).getvalue()
            file_spec = FileSpec(name=self.__error_outfile,
                                 contents=contents,
                                 content_type='text/csv',
                                 size=len(contents))

            # TODO: is the project the right place to write this file to?
            self.__project.upload_file(file_spec)  # type: ignore


def main():
    """Main method for Regression Curator."""

    GearEngine.create_with_parameter_store().run(
        gear_type=RegressionCuratorVisitor)


if __name__ == "__main__":
    main()
