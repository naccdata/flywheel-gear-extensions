"""Entry script for Gather Form Data."""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from data_requests.data_request import ModuleDataGatherer
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

from gather_form_data_app.main import GatherConfig, run

log = logging.getLogger(__name__)


def _write_module_output(
    context: GearContext,
    gatherers: list[ModuleDataGatherer],
    output_prefix: str,
) -> None:
    """Writes the data content in each gatherer to one or more output files.

    For gatherers with ``split_by_formver=False`` (default), produces a single
    CSV per module named ``{output_prefix}-{module}-{date}.csv``.

    For gatherers with ``split_by_formver=True``, produces one CSV per
    (module, formver) pair, named
    ``{output_prefix}-{module}-{formver_label}-{date}.csv`` (e.g.
    ``adrc-UDS-v4-2026-05-29.csv``). The formver label is normalized via
    ``formver_label`` (e.g. "1.0" -> "v1", missing -> "unknown").

    Args:
      context: the gear context
      gatherers: a list of ModuleDataGatherer objects
      output_prefix: the prefix used in output filenames
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
                    f"{output_prefix}-{gatherer.module_name}-"
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

        output_filename = f"{output_prefix}-{gatherer.module_name}-{today}.csv"
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
        modules: set[str],
        study_id: str,
        output_prefix: str,
        formver_split: bool = False,
        batch_size: int = 100,
        reload_workers: int = 10,
    ):
        super().__init__(client=client)
        self.__file_input = file_input
        self.__project_names: list[str] = project_names
        self.__info_paths = info_paths
        self.__modules = modules
        self.__study_id = study_id
        self.__output_prefix = output_prefix
        self.__formver_split = formver_split
        self.__batch_size = batch_size
        self.__reload_workers = reload_workers

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
          GearExecutionError if any expected inputs are missing or config
          parameters are invalid
        """
        client = GearBotClient.create(context=context, parameter_store=parameter_store)
        file_input = InputFileWrapper.create(input_name="input_file", context=context)
        assert file_input, "create raises exception if missing input file"

        options = context.config.opts
        project_names = options.get("project_names", "").split(",")
        include_derived = options.get("include_derived", False)
        info_paths = ["forms.json", "derived"] if include_derived else ["forms.json"]
        modules = set(options.get("modules", "").split(","))

        study_id = options.get("study_id", "adrc")
        formver_split = options.get("formver_split", False)
        output_file_prefix = options.get("output_file_prefix", "")
        output_prefix = output_file_prefix if output_file_prefix else study_id

        batch_size = options.get("batch_size", 100)
        reload_workers = options.get("reload_workers", 10)

        if batch_size <= 0:
            raise GearExecutionError(
                f"batch_size must be a positive integer, got {batch_size}"
            )
        if reload_workers <= 0:
            raise GearExecutionError(
                f"reload_workers must be a positive integer, got {reload_workers}"
            )

        return GatherFormDataVisitor(
            client=client,
            file_input=file_input,
            project_names=project_names,
            info_paths=info_paths,
            modules=modules,
            study_id=study_id,
            output_prefix=output_prefix,
            formver_split=formver_split,
            batch_size=batch_size,
            reload_workers=reload_workers,
        )

    def run(self, context: GearContext) -> None:
        input_path = Path(self.__file_input.filepath)
        with open(input_path, mode="r", encoding="utf-8-sig") as request_file:
            file_id = self.__file_input.file_id
            error_writer = ListErrorWriter(
                container_id=file_id,
                fw_path=self.proxy.get_lookup_path(self.proxy.get_file(file_id)),
            )

            success, data_gatherers = run(
                request_file=request_file,
                proxy=self.proxy,
                config=GatherConfig(
                    study_id=self.__study_id,
                    project_names=self.__project_names,
                    modules=self.__modules,
                    info_paths=self.__info_paths,
                    batch_size=self.__batch_size,
                    reload_workers=self.__reload_workers,
                    formver_split=self.__formver_split,
                ),
                error_writer=error_writer,
            )

            if success:
                _write_module_output(
                    context=context,
                    gatherers=data_gatherers,
                    output_prefix=self.__output_prefix,
                )

        context.metadata.add_qc_result(
            self.__file_input.file_input,
            name="validation",
            state="PASS" if success else "FAIL",
            data=error_writer.errors().model_dump(by_alias=True),
        )

        gear_name = self.get_gear_name(context, "gather-form-data")
        context.metadata.add_file_tags(self.__file_input.file_input, tags=gear_name)


def main():
    """Main method for Gather Form Data."""
    engine = GearEngine().create_with_parameter_store()
    engine.run(gear_type=GatherFormDataVisitor)


if __name__ == "__main__":
    main()
