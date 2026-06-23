"""Entry script for Gather Form Data."""

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional, get_args

from data_requests.data_request import (
    DataRequestMatch,
    DataRequestVisitor,
    ModuleDataGatherer,
)
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
from outputs.error_writer import ListErrorWriter
from pydantic import ValidationError

from gather_form_data_app.main import ProjectModeConfig, run, run_project_mode

ModuleName = str

log = logging.getLogger(__name__)


def _write_module_output(
    context: GearContext,
    gatherers: list[ModuleDataGatherer],
    study_id: str,
) -> None:
    """Writes the data content in each gatherer to one or more output files.

    For gatherers with ``split_by_formver=False`` (default), produces a single
    CSV per module named ``{study_id}-{module}-{date}.csv``.

    For gatherers with ``split_by_formver=True``, produces one CSV per
    (module, formver) pair, named
    ``{study_id}-{module}-{formver_label}-{date}.csv`` (e.g.
    ``adrc-UDS-v4-2026-05-29.csv``). The formver label is normalized via
    ``formver_label`` (e.g. "1.0" -> "v1", missing -> "unknown").

    Args:
      context: the gear context
      gatherers: a list of ModuleDataGatherer objects
      study_id: the study identifier used in output filenames
    """
    today = date.today().isoformat()
    for gatherer in gatherers:
        if gatherer.split_by_formver:
            buckets = gatherer.content_by_formver
            if not buckets:
                log.warning(
                    "skipping output for module %s: no data found",
                    gatherer.module_name,
                )
                continue
            for formver_label_value, content in buckets.items():
                if not content:
                    continue
                output_filename = (
                    f"{study_id}-{gatherer.module_name}-"
                    f"{formver_label_value}-{today}.csv"
                )
                with context.open_output(
                    output_filename, mode="w", encoding="utf-8"
                ) as output_file:
                    output_file.write(content)
            continue

        if not gatherer.content:
            log.warning(
                "skipping output for module %s: no data found",
                gatherer.module_name,
            )
            continue

        output_filename = f"{study_id}-{gatherer.module_name}-{today}.csv"
        with context.open_output(
            output_filename, mode="w", encoding="utf-8"
        ) as output_file:
            output_file.write(gatherer.content)


class GatherFormDataVisitor(GearExecutionEnvironment):
    """Visitor for the Gather Form Data gear."""

    def __init__(
        self,
        client: ClientWrapper,
        file_input: InputFileWrapper,
        project_names: list[str],
        info_paths: list[str],
        modules: set[ModuleName],
        study_id: str,
        formver_split: bool = False,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__project_names: list[str] = project_names
        self.__info_paths = info_paths
        self.__modules = modules
        self.__study_id = study_id
        self.__formver_split = formver_split

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "GatherFormDataVisitor":
        """Creates a Gather Form Data execution visitor.

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
        project_names = options.get("project_names", "").split(",")
        include_derived = options.get("include_derived", False)
        info_paths = ["forms.json", "derived"] if include_derived else ["forms.json"]
        modules = options.get("modules", "").split(",")
        unexpected_modules = [
            module for module in modules if module not in get_args(ModuleName)
        ]
        if unexpected_modules:
            log.warning("ignoring unexpected modules: %s", ",".join(unexpected_modules))

        study_id = options.get("study_id", "adrc")
        formver_split = options.get("formver_split", False)

        return GatherFormDataVisitor(
            client=client,
            file_input=file_input,
            project_names=project_names,
            info_paths=info_paths,
            modules={module for module in get_args(ModuleName) if module in modules},
            study_id=study_id,
            formver_split=formver_split,
        )

    def run(self, context: GearContext) -> None:
        data_gatherers: list[ModuleDataGatherer] = []
        for module_name in self.__modules:
            data_gatherers.append(
                ModuleDataGatherer(
                    proxy=self.proxy,
                    module_name=module_name,
                    info_paths=self.__info_paths,
                    split_by_formver=self.__formver_split,
                )
            )

        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode="r", encoding="utf-8-sig") as request_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
            )
            request_visitor = DataRequestVisitor(
                proxy=self.proxy,
                study_id=self.__study_id,
                project_names=self.__project_names,
                gatherers=data_gatherers,
                error_writer=error_writer,
            )

            success = run(
                request_file=request_file,
                request_visitor=request_visitor,
                error_writer=error_writer,
            )
            if success:
                _write_module_output(
                    context=context,
                    gatherers=request_visitor.gatherers,
                    study_id=self.__study_id,
                )

        context.metadata.add_qc_result(
            self.__file_input.file_input,
            name="validation",
            state="PASS" if success else "FAIL",
            data=error_writer.errors().model_dump(by_alias=True),
        )

        gear_name = self.get_gear_name(context, "gather-submission-status")
        context.metadata.add_file_tags(self.__file_input.file_input, tags=gear_name)


class ProjectModeVisitor(GearExecutionEnvironment):
    """Visitor for project-mode execution of Gather Form Data."""

    def __init__(
        self,
        client: ClientWrapper,
        group_id: str,
        project_name: str,
        info_paths: list[str],
        modules: set[str],
        study_id: str,
        formver_split: bool = False,
    ):
        super().__init__(client=client)
        self.__group_id = group_id
        self.__project_name = project_name
        self.__info_paths = info_paths
        self.__modules = modules
        self.__study_id = study_id
        self.__formver_split = formver_split

    @classmethod
    def create(
        cls,
        context: GearContext,
        parameter_store: Optional[ParameterStore] = None,
    ) -> "ProjectModeVisitor":
        """Creates a ProjectModeVisitor execution visitor.

        Extracts project mode configuration from the gear context,
        validates it with ProjectModeConfig, and returns the visitor.

        Args:
            context: The gear context.
            parameter_store: The parameter store
        Returns:
          the execution environment
        Raises:
          GearExecutionError if configuration is invalid
        """
        client = GearBotClient.create(context=context, parameter_store=parameter_store)

        options = context.config.opts
        group_id = options.get("group_id", "")
        project_name = options.get("project_name", "")
        modules_str = options.get("modules", "")
        modules = set(modules_str.split(",")) if modules_str else set()
        include_derived = options.get("include_derived", False)
        info_paths = ["forms.json", "derived"] if include_derived else ["forms.json"]
        study_id = options.get("study_id", "adrc")
        formver_split = options.get("formver_split", False)

        try:
            config = ProjectModeConfig(
                group_id=group_id,
                project_name=project_name,
                modules=modules,
                info_paths=info_paths,
                study_id=study_id,
            )
        except ValidationError as error:
            raise GearExecutionError(
                f"Invalid project mode configuration: {error}"
            ) from error

        return ProjectModeVisitor(
            client=client,
            group_id=config.group_id,
            project_name=config.project_name,
            info_paths=config.info_paths,
            modules=config.modules,
            study_id=config.study_id,
            formver_split=formver_split,
        )

    def run(self, context: GearContext) -> None:
        """Run project mode execution.

        Resolves group/project, iterates subjects, gathers data, and
        writes output files.

        Raises:
          GearExecutionError if the group or project cannot be found.
        """
        group = self.proxy.find_group(self.__group_id)
        if not group:
            raise GearExecutionError(f"Group not found: {self.__group_id}")

        project = group.find_project(self.__project_name)
        if not project:
            raise GearExecutionError(
                f"Project not found: {self.__project_name} in group {self.__group_id}"
            )

        subjects = list(project.project.subjects.iter())
        if not subjects:
            log.warning(
                "No subjects found in project %s/%s",
                self.__group_id,
                self.__project_name,
            )
            return

        requests = [
            DataRequestMatch(
                naccid=subject.label,
                subject_id=subject.id,
                project_label=project.label,
            )
            for subject in subjects
        ]

        gatherers = [
            ModuleDataGatherer(
                proxy=self.proxy,
                module_name=module_name,
                info_paths=self.__info_paths,
                split_by_formver=self.__formver_split,
            )
            for module_name in self.__modules
        ]

        run_project_mode(requests=requests, gatherers=gatherers)

        _write_module_output(
            context=context,
            gatherers=gatherers,
            study_id=self.__study_id,
        )


def main():
    """Main method for Gather Form Data.

    Determines the execution mode from gear configuration and dispatches
    to the appropriate visitor. The GearEngine opens its own GearContext
    internally, so we peek at config here only to select the mode.
    """
    engine = GearEngine().create_with_parameter_store()

    with GearContext() as context:
        execution_mode = context.config.opts.get("execution_mode", "participant_list")
        input_file_path = context.config.get_input_path("input_file")

    if execution_mode == "project":
        engine.run(gear_type=ProjectModeVisitor)
    elif execution_mode == "participant_list":
        if not input_file_path:
            log.error("input_file is required when execution_mode is participant_list")
            sys.exit(1)
        engine.run(gear_type=GatherFormDataVisitor)
    else:
        log.error("Invalid execution_mode: %s", execution_mode)
        sys.exit(1)


if __name__ == "__main__":
    main()
