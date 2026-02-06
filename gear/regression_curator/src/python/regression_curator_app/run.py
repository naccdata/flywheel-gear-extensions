"""Entry script for Regression Curator."""

import logging
from multiprocessing import Manager
from typing import List, Optional

from curator.scheduling import ProjectCurationError, ProjectCurationScheduler
from flywheel import FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from fw_gear import GearContext
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
from nacc_common.error_models import FileError
from outputs.error_writer import ManagerListErrorWriter
from outputs.outputs import write_csv_to_stream
from utils.utils import parse_string_to_list

from regression_curator_app.main import run

log = logging.getLogger(__name__)


class RegressionCuratorVisitor(GearExecutionEnvironment):
    """Visitor for the Regression Curator gear."""

    def __init__(
        self,
        client: ClientWrapper,
        project: ProjectAdaptor,
        s3_qaf_file: str,
        filename_patterns: List[str],
        error_outfile: str,
        s3_mqt_file: Optional[str] = None,
        naccid_blacklist_file: Optional[InputFileWrapper] = None,
        variable_blacklist_file: Optional[InputFileWrapper] = None,
    ):
        super().__init__(client=client)
        self.__project = project
        self.__s3_qaf_file = s3_qaf_file
        self.__s3_mqt_file = s3_mqt_file
        self.__filename_patterns = filename_patterns
        self.__error_outfile = error_outfile
        self.__naccid_blacklist_file = naccid_blacklist_file
        self.__variable_blacklist_file = variable_blacklist_file

    @classmethod
    def create(
        cls,
        context: GearContext,
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

        options = context.config.opts
        s3_qaf_file = options.get("s3_qaf_file", None)
        s3_mqt_file = options.get("s3_mqt_file", None)

        if not s3_qaf_file:
            raise GearExecutionError("QAF file missing")

        filename_patterns = parse_string_to_list(
            options.get("filename_patterns", ".*UDS\\.json")
        )

        proxy = client.get_proxy()
        fw_project = get_project_from_destination(context=context, proxy=proxy)
        project = ProjectAdaptor(project=fw_project, proxy=proxy)

        error_outfile = options.get("error_outfile", "regression_errors.csv")

        naccid_blacklist_file = InputFileWrapper.create(
            input_name="naccid_blacklist_file", context=context
        )
        variable_blacklist_file = InputFileWrapper.create(
            input_name="variable_blacklist_file", context=context
        )

        if options.get("debug", False):
            logging.basicConfig(level=logging.DEBUG)

        return RegressionCuratorVisitor(
            client=client,
            project=project,
            s3_qaf_file=s3_qaf_file,
            s3_mqt_file=s3_mqt_file,
            filename_patterns=filename_patterns,
            error_outfile=error_outfile,
            naccid_blacklist_file=naccid_blacklist_file,
            variable_blacklist_file=variable_blacklist_file,
        )

    def run(self, context: GearContext) -> None:
        try:
            fw_path = self.proxy.get_lookup_path(self.__project.project)
        except ApiException as error:
            raise GearExecutionError(
                f"Failed to find the input file: {error}"
            ) from error

        error_writer = ManagerListErrorWriter(
            container_id=self.__project.id, fw_path=fw_path, errors=Manager().list()
        )

        naccid_blacklist = set([])
        if self.__naccid_blacklist_file:
            with open(self.__naccid_blacklist_file.filepath, mode="r") as fh:
                naccid_blacklist = set([x.strip() for x in fh.readlines()])

        try:
            scheduler = ProjectCurationScheduler.create(
                project=self.__project,
                filename_patterns=self.__filename_patterns,
            )
        except ProjectCurationError as error:
            raise GearExecutionError(error) from error

        variable_blacklist = set([])
        if self.__variable_blacklist_file:
            with open(self.__variable_blacklist_file.filepath, mode="r") as fh:
                variable_blacklist = set([x.strip() for x in fh.readlines()])

        # to avoid loading the entire baseline files (which explode memory
        # usage), only load NACCIDs relevant to this curation. unfortunately
        # this means we have to query each subject ID to get its corresponding
        # label, which is slow if there are a lot of subjects.
        # probably better way to do this but for the purposes of
        # regression testing gets the job done
        subjects = []
        for subject_id in scheduler.get_subject_ids():
            subject = self.__project.get_subject_by_id(subject_id)
            if subject:
                if subject.label in naccid_blacklist:
                    log.info(
                        f"{subject.label} in blacklist, removing from "
                        + "regression testing"
                    )
                    continue

                subjects.append(subject.label)

        run(
            context=context,
            subjects=subjects,
            s3_qaf_file=self.__s3_qaf_file,
            s3_mqt_file=self.__s3_mqt_file,
            scheduler=scheduler,
            error_writer=error_writer,
            variable_blacklist=variable_blacklist,
        )

        errors = list(error_writer.errors())

        if errors:
            log.error(
                f"{len(errors)} errors detected, writing errors to "
                + f"output file {self.__error_outfile}"
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
        else:
            log.info("No errors detected!")


def main():
    """Main method for Regression Curator."""

    GearEngine.create_with_parameter_store().run(gear_type=RegressionCuratorVisitor)


if __name__ == "__main__":
    main()
