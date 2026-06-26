"""Entry script for Center Form Export."""

import logging
from datetime import date
from typing import Optional

from data_requests.data_request import DataRequestMatch, ModuleDataGatherer
from fw_gear import GearContext
from gear_execution.gear_execution import (
    ClientWrapper,
    GearBotClient,
    GearEngine,
    GearExecutionEnvironment,
    GearExecutionError,
)
from inputs.parameter_store import ParameterStore

from center_form_export_app.main import run

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


class CenterFormExportVisitor(GearExecutionEnvironment):
    """Visitor for the Center Form Export gear."""

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
    ) -> "CenterFormExportVisitor":
        """Creates a CenterFormExportVisitor execution visitor.

        Extracts configuration from the gear context, validates required
        fields, and returns the visitor.

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
        group_id = options.get("group_id", "").strip()
        project_name = options.get("project_name", "").strip()
        modules_str = options.get("modules", "")
        modules = {m.strip() for m in modules_str.split(",") if m.strip()}
        include_derived = options.get("include_derived", False)
        info_paths = ["forms.json", "derived"] if include_derived else ["forms.json"]
        study_id = options.get("study_id", "adrc")
        formver_split = options.get("formver_split", False)

        if not group_id:
            raise GearExecutionError("group_id must not be empty")
        if not project_name:
            raise GearExecutionError("project_name must not be empty")
        if not modules:
            raise GearExecutionError("at least one module must be specified")

        return CenterFormExportVisitor(
            client=client,
            group_id=group_id,
            project_name=project_name,
            info_paths=info_paths,
            modules=modules,
            study_id=study_id,
            formver_split=formver_split,
        )

    def run(self, context: GearContext) -> None:
        """Runs the center form export.

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

        run(requests=requests, gatherers=gatherers)

        _write_module_output(
            context=context,
            gatherers=gatherers,
            study_id=self.__study_id,
        )


def main():
    """Main method for Center Form Export."""
    GearEngine().create_with_parameter_store().run(gear_type=CenterFormExportVisitor)


if __name__ == "__main__":
    main()
