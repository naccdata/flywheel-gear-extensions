"""Entry script for Gather Submission Status."""

import logging
from csv import DictWriter
from pathlib import Path
from typing import Any, List, Optional

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
    status_report_visitor_builder,
)
from outputs.error_writer import ListErrorWriter

from gather_submission_status_app.main import (
    CONSOLIDATED_FIELDNAMES,
    run,
    run_consolidated,
)

log = logging.getLogger(__name__)


class GatherSubmissionStatusVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Submission Status gear."""

    def __init__(
        self,
        client: ClientWrapper,
        admin_id: str,
        file_input: InputFileWrapper,
        project_names: List[str],
        modules: set[str],
        study_id: str,
        file_visitor_builder: FileQCReportVisitorBuilder,
        fieldnames: List[str],
        reload_workers: int,
        query_type: str,
        passed_output_file: str,
        failed_output_file: str,
    ):
        super().__init__(client=client)
        self.__admin_id = admin_id
        self.__file_input = file_input
        self.__project_names = project_names
        self.__modules = modules
        self.__study_id = study_id
        self.__file_visitor_builder = file_visitor_builder
        self.__report_fieldnames = fieldnames
        self.__reload_workers = reload_workers
        self.__query_type = query_type
        self.__passed_output_file = passed_output_file
        self.__failed_output_file = failed_output_file

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
        passed_output_file = options.get(
            "passed_output_file", "submission-status-passed.csv"
        )
        failed_output_file = options.get(
            "failed_output_file", "submission-status-failed.csv"
        )
        admin_id = options.get("admin_group", DefaultValues.NACC_GROUP_ID)
        project_names = options.get("project_names", "").split(",")
        modules = set(options.get("modules", "").split(","))

        study_id = options.get("study_id", "adrc")

        reload_workers = int(options.get("reload_workers", 10))
        if reload_workers <= 0:
            raise GearExecutionError(
                f"reload_workers must be a positive integer, got {reload_workers}"
            )

        query_type_arg = options.get("query_type", "status")
        if query_type_arg not in ["error", "status"]:
            raise GearExecutionError(f"Invalid query_type: {query_type_arg}")

        query_type = query_type_arg if query_type_arg == "error" else "status"

        file_visitor_builder: FileQCReportVisitorBuilder = status_report_visitor_builder
        fieldnames = CONSOLIDATED_FIELDNAMES

        if query_type == "error":
            file_visitor_builder = error_report_visitor_builder
            fieldnames = ErrorReportModel.serialized_fieldnames()

        return GatherSubmissionStatusVisitor(
            client=client,
            file_input=file_input,
            admin_id=admin_id,
            project_names=project_names,
            modules=modules,
            study_id=study_id,
            file_visitor_builder=file_visitor_builder,
            fieldnames=fieldnames,
            reload_workers=reload_workers,
            query_type=query_type,
            passed_output_file=passed_output_file,
            failed_output_file=failed_output_file,
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

            if self.__query_type == "error":
                success = self._run_error_report(
                    context=context,
                    csv_file=csv_file,
                    clustering=clustering,
                    error_writer=error_writer,
                )
            else:
                success = self._run_status_report(
                    context=context,
                    csv_file=csv_file,
                    clustering=clustering,
                    error_writer=error_writer,
                )

            context.metadata.add_qc_result(
                self.__file_input.file_input,
                name="validation",
                state="PASS" if success else "FAIL",
                data=error_writer.errors().model_dump(by_alias=True),
            )

            gear_name = self.get_gear_name(context, "gather-submission-status")
            context.metadata.add_file_tags(self.__file_input.file_input, tags=gear_name)

    def _run_error_report(
        self,
        *,
        context: GearContext,
        csv_file: Any,
        clustering: StatusRequestClusteringVisitor,
        error_writer: ListErrorWriter,
    ) -> bool:
        """Run the error report query type (writes a single output file).

        Args:
            context: the gear execution context
            csv_file: the open CSV input file
            clustering: the clustering visitor
            error_writer: collects per-request errors

        Returns:
            True if processing succeeded
        """
        with context.open_output(
            self.__passed_output_file, mode="w", encoding="utf-8"
        ) as output_file:
            writer = DictWriter(output_file, fieldnames=self.__report_fieldnames)
            writer.writeheader()
            return run(
                input_file=csv_file,
                modules=self.__modules,
                clustering_visitor=clustering,
                file_visitor_builder=self.__file_visitor_builder,
                writer=writer,
                error_writer=error_writer,
                reload_workers=self.__reload_workers,
            )

    def _run_status_report(
        self,
        *,
        context: GearContext,
        csv_file: Any,
        clustering: StatusRequestClusteringVisitor,
        error_writer: ListErrorWriter,
    ) -> bool:
        """Run the status report query type (writes passed and failed files).

        Consolidates per-stage rows into per-(ptid, visit, module) and
        writes separate output files for passed and failed submissions.

        Args:
            context: the gear execution context
            csv_file: the open CSV input file
            clustering: the clustering visitor
            error_writer: collects per-request errors

        Returns:
            True if processing succeeded
        """
        success, result = run_consolidated(
            input_file=csv_file,
            modules=self.__modules,
            clustering_visitor=clustering,
            file_visitor_builder=self.__file_visitor_builder,
            error_writer=error_writer,
            reload_workers=self.__reload_workers,
        )

        if not success:
            return False

        fieldnames = self.__report_fieldnames

        with context.open_output(
            self.__passed_output_file, mode="w", encoding="utf-8"
        ) as passed_file:
            writer = DictWriter(passed_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in result.passed:
                writer.writerow(row)

        with context.open_output(
            self.__failed_output_file, mode="w", encoding="utf-8"
        ) as failed_file:
            writer = DictWriter(failed_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in result.failed:
                writer.writerow(row)

        return True


def main():
    """Main method for Gather Submission Status."""

    GearEngine().create_with_parameter_store().run(
        gear_type=GatherSubmissionStatusVisitor
    )


if __name__ == "__main__":
    main()
