"""Entry script for Gather Submission Status."""

import logging
from csv import DictWriter
from pathlib import Path
from typing import List, Optional, get_args

from data_requests.status_request import StatusRequestClusteringVisitor
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
from keys.keys import DefaultValues
from nacc_common.qc_report import (
    FileQCReportVisitorBuilder,
)
from nacc_common.visit_submission_error import (
    ErrorReportModel,
    error_report_visitor_builder,
)
from nacc_common.visit_submission_status import (
    StatusReportModel,
    status_report_visitor_builder,
)
from outputs.error_writer import ListErrorWriter

from gather_submission_status_app.main import ModuleName, run

log = logging.getLogger(__name__)


class GatherSubmissionStatusVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Submission Status gear."""

    def __init__(
        self,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        output_filename: str,
        project_names: List[str],
        modules: set[ModuleName],
        study_id: str,
        file_visitor_builder: FileQCReportVisitorBuilder,
        fieldnames: List[str],
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__output_filename = output_filename
        self.__project_names = project_names
        self.__modules = modules
        self.__study_id = study_id
        self.__file_visitor_builder = file_visitor_builder
        self.__report_fieldnames = fieldnames

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "GatherSubmissionStatusVisitor":
        """Creates a Gather Submission Status execution visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if any expected inputs are missing
        """

        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing input file"

        options = context.config.opts
        output_filename = options.get("output_file", "submission-status.csv")
        admin_id = options.get("admin_group", DefaultValues.NACC_GROUP_ID)
        project_names = options.get("project_names", "").split(",")
        modules = options.get("modules", "").split(",")
        unexpected_modules = [
            module for module in modules if module not in get_args(ModuleName)
        ]
        if unexpected_modules:
            log.warning("ignoring unexpected modules: %s", ",".join(unexpected_modules))

        study_id = options.get("study_id", "adrc")

        query_type_arg = options.get("query_type", "status")
        if query_type_arg not in ["error", "status"]:
            raise GearExecutionError(f"Invalid query_type: {query_type_arg}")

        query_type = query_type_arg if query_type_arg == "error" else "status"

        file_visitor_builder: FileQCReportVisitorBuilder = status_report_visitor_builder
        fieldnames = list(StatusReportModel.model_fields.keys())

        if query_type == "error":
            file_visitor_builder = error_report_visitor_builder
            fieldnames = ErrorReportModel.serialized_fieldnames()

        return GatherSubmissionStatusVisitor(
            client=client,
            file_input=file_input,
            output_filename=output_filename,
            admin_id=admin_id,
            project_names=project_names,
            modules={module for module in get_args(ModuleName) if module in modules},
            study_id=study_id,
            file_visitor_builder=file_visitor_builder,
            fieldnames=fieldnames,
        )

    def run(self, context: GearContext) -> None:
        """Runs the gather-submission-status app.

        Args:
          context: the gear execution context
        """

        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode="r", encoding="utf-8-sig") as csv_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
            )

            clustering = StatusRequestClusteringVisitor(
                proxy=self.proxy,
                study_id=self.__study_id,
                project_names=self.__project_names,
                error_writer=error_writer,
            )
            with context.open_output(
                self.__output_filename, mode="w", encoding="utf-8"
            ) as status_file:
                writer = DictWriter(status_file, fieldnames=self.__report_fieldnames)
                writer.writeheader()
                success = run(
                    input_file=csv_file,
                    modules=self.__modules,
                    clustering_visitor=clustering,
                    file_visitor_builder=self.__file_visitor_builder,
                    writer=writer,
                    error_writer=error_writer,
                )

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors().model_dump(by_alias=True),
            )

            gear_name = self.gear_name(context, "gather-submission-status")
            context.metadata.add_file_tags(self.__file_input.file_input, tags=gear_name)


def main():
    """Main method for Gather Submission Status."""

    GearEngine().create_with_parameter_store().run(
        gear_type=GatherSubmissionStatusVisitor
    )


if __name__ == "__main__":
    main()
