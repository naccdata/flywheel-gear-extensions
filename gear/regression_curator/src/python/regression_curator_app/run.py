"""Entry script for Regression Curator."""

import logging
from multiprocessing import Manager
from typing import Any, Dict, List, MutableSequence, Optional

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
    InputFileWrapper,
    get_project_from_destination,
)
from inputs.parameter_store import ParameterStore
from outputs.error_models import FileError
from outputs.error_writer import UserErrorWriter
from outputs.outputs import write_csv_to_stream
from utils.utils import parse_string_to_list

from regression_curator_app.main import run

log = logging.getLogger(__name__)


class ManagerListErrorWriter(UserErrorWriter):
    """Manages errors as dictionary objects to be compatible with
    multiprocessing."""

    def __init__(
        self,
        container_id: str,
        fw_path: str,
        errors: Optional[MutableSequence[Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(container_id, fw_path)
        self.__errors = [] if errors is None else errors

    def write(self, error: FileError, set_timestamp: bool = True) -> None:
        """Captures error for writing to metadata.

        Args:
          error: the file error object
          set_timestamp: if True, assign the writer timestamp to the error
        """
        self.prepare_error(error, set_timestamp)
        self.__errors.append(error.model_dump(by_alias=True))

    def errors(self) -> MutableSequence[Dict[str, Any]]:
        """Returns serialized list of accumulated file errors.

        Returns:
          List of serialized FileError objects
        """
        return self.__errors

    def clear(self):
        """Clear the errors list."""
        self.__errors.clear()


class RegressionCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the Regression Curator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        project: ProjectAdaptor,
        s3_qaf_file: str,
        keep_fields: List[str],
        filename_pattern: str,
        error_outfile: str,
        s3_mqt_file: Optional[str] = None,
        blacklist_file: Optional[InputFileWrapper] = None,
    ):
        super().__init__(client=client)
        self.__project = project
        self.__s3_qaf_file = s3_qaf_file
        self.__s3_mqt_file = s3_mqt_file
        self.__keep_fields = keep_fields
        self.__filename_pattern = filename_pattern
        self.__error_outfile = error_outfile
        self.__blacklist_file = blacklist_file

    @classmethod
    def create(
        cls,
        context: GearToolkitContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "RegressionCuratorVisitor":
        """Creates a Regression Curator execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        s3_qaf_file = context.config.get("s3_qaf_file", None)
        s3_mqt_file = context.config.get("s3_mqt_file", None)

        if not s3_qaf_file:
            raise GearExecutionError("QAF file missing")

        keep_fields = parse_string_to_list(context.config.get("keep_fields", ""))
        filename_pattern = context.config.get("filename_pattern", "*UDS.json")

        proxy = client.get_proxy()
        fw_project = get_project_from_destination(context=context, proxy=proxy)
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        error_outfile = context.config.get("error_outfile", "regression_errors.csv")

        blacklist_file = InputFileWrapper.create(
            input_name="blacklist_file", context=context
        )

        if context.config.get("debug", False):
            logging.basicConfig(level=logging.DEBUG)

        return RegressionCuratorVisitor(
            client=client,
            project=project,
            s3_qaf_file=s3_qaf_file,
            s3_mqt_file=s3_mqt_file,
            keep_fields=keep_fields,
            filename_pattern=filename_pattern,
            error_outfile=error_outfile,
            blacklist_file=blacklist_file,
        )

    def run(self, context: GearToolkitContext) -> None:
        try:
            fw_path = self.proxy.get_lookup_path(self.__project.project)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        error_writer = ManagerListErrorWriter(
            container_id=self.__project.id, fw_path=fw_path, errors=Manager().list()
        )

        blacklist = None
        if self.__blacklist_file:
            with open(self.__blacklist_file.filepath, mode="r") as fh:
                blacklist = [x.strip() for x in fh.readlines()]

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                filename_pattern=self.__filename_pattern,
                blacklist=blacklist,
            )
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        run(
            context=context,
            s3_qaf_file=self.__s3_qaf_file,
            s3_mqt_file=self.__s3_mqt_file,
            keep_fields=self.__keep_fields,
            scheduler=scheduler,
            error_writer=error_writer,
        )

        errors = list(error_writer.errors())

        if errors:
            log.error(
                f"Errors detected, writing errors to output file {self.__error_outfile}"
            )
            contents = write_csv_to_stream(
                headers=FileError.fieldnames(), data=errors
            ).getvalue()
            file_spec = FileSpec(
                name=self.__error_outfile,
                contents=contents,
                content_type="text/csv",
                size=len(contents),
            )

            # TODO: is the project the right place to write this file to?
            self.__project.upload_file(file_spec)  # type: ignore


def main():
    """Main method for Regression Curator."""

    GearEngine.create_with_parameter_store().run(gear_type=RegressionCuratorVisitor)


if __name__ == "__main__":
    main()
