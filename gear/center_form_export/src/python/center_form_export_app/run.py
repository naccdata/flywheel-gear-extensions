"""Entry script for Center Form Export."""

import logging
import re
from datetime import date
from typing import Optional

from data_requests.data_request import ModuleDataGatherer
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
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

DEFAULT_GEAR_NAME = "center-form-export"

# A caller-supplied value that becomes a filename segment in a
# '-'-delimited name must not contain a delimiter. It must not contain a
# '.' either, which confuses the extension. Consumers parse these names
# with anchored regexes. Anything outside this charset makes the
# surrounding segments ambiguous.
#
# The formver segment is the one exception, and is not checked here: it is
# derived from the form data rather than supplied by a caller, and can
# carry a '.', as in LBD "v3.1". That segment sits in a fixed, non-final
# position, where a '.' cannot be read as a segment boundary.
# ``formver_label`` guarantees its charset at the point it is produced.
FILENAME_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9]+$")
STUDY_ID_MAX_LENGTH = 16
RUN_ID_MAX_LENGTH = 32
SOURCE_ID_MAX_LENGTH = 16
MODULE_NAME_MAX_LENGTH = 16


def _validate_filename_segment(
    name: str, value: str, max_length: int, required: bool = False
) -> None:
    """Validates a caller-supplied value used as an output filename segment.

    Every config field that reaches a filename is checked here. If a value
    corrupts the name, the job fails at startup with a clear message,
    rather than producing output no consumer can attribute.

    An empty value is rejected only when ``required``. An omitted optional
    field contributes no segment at all, which leaves the name parseable.
    An empty required field emits a doubled separator, which does not.

    Args:
      name: the config field name, used in error messages
      value: the caller-supplied value, possibly empty
      max_length: the maximum length permitted for this field
      required: whether an empty value is an error
    Raises:
      GearExecutionError if the value is not usable as a filename segment
    """
    if required and not value:
        raise GearExecutionError(f"{name} must not be empty")
    if value and not FILENAME_SEGMENT_PATTERN.match(value):
        raise GearExecutionError(
            f"{name} must contain only letters and digits, got {value!r}"
        )
    if len(value) > max_length:
        raise GearExecutionError(
            f"{name} must be at most {max_length} characters, got {len(value)}"
        )


def _output_stamp(run_date: str, run_id: str) -> str:
    """Returns the per-run filename stamp.

    Args:
      run_date: the run's date, ISO formatted, computed once per gear run
      run_id: the caller-supplied run identifier, possibly empty
    Returns:
      the date alone when no run_id was supplied, otherwise the date
      followed by the run_id
    """
    return f"{run_date}-{run_id}" if run_id else run_date


def _destination_group_id(context: GearContext, proxy: FlywheelProxy) -> str:
    """Returns the group id of the container this job writes its output to.

    Args:
      context: the gear context
      proxy: the Flywheel proxy used to resolve the container
    Returns:
      the group id owning the job's destination container
    Raises:
      GearExecutionError if the destination cannot be resolved to a group
    """
    destination = context.config.destination or {}
    container_id = destination.get("id")
    if not container_id:
        raise GearExecutionError(
            "Unable to determine the job's destination container; "
            "refusing to run without one"
        )

    try:
        container = proxy.get_container_by_id(container_id)
    except Exception as error:
        raise GearExecutionError(
            f"Unable to resolve destination container {container_id}: {error}"
        ) from error

    parents = getattr(container, "parents", None)
    group_id = getattr(parents, "group", None) or getattr(container, "group", None)
    if not group_id:
        raise GearExecutionError(
            f"Destination container {container_id} has no group; refusing to run"
        )

    return str(group_id)


def _check_destination_group(
    context: GearContext, proxy: FlywheelProxy, group_id: str
) -> None:
    """Refuses a job whose destination is outside the group it reads.

    The gear reads whatever group and project its config names, using
    GearBot's key, which can read every center. Nothing in the job itself
    constrains that to the caller's own center. Without this check, anyone
    able to run the gear can point it at another center's project, and
    have that center's records written as CSVs somewhere they can download
    from.

    Comparing the destination's group with the configured ``group_id``
    closes that path for every trigger mechanism, rather than relying on
    the caller to submit an honest config. It is defense in depth, not a
    replacement for Flywheel permissions.

    The check runs before the source group or project is resolved and
    before any data is gathered, so a refused run reads nothing, writes
    nothing, and reveals nothing about the project it was aimed at. It
    fails closed: a destination whose group cannot be determined is
    refused rather than allowed through unchecked.

    A same-group check is deliberately all this does. Study-level scoping
    -- an ``adrc`` export landing in a ``distribution-form-dvcid``
    project -- is the caller's concern, since only the caller knows which
    study a run belongs to.

    Args:
      context: the gear context
      proxy: the Flywheel proxy used to resolve the destination
      group_id: the group named in the gear config, which the gear reads
    Raises:
      GearExecutionError if the destination is in a different group
    """
    destination_group_id = _destination_group_id(context=context, proxy=proxy)
    if destination_group_id != group_id:
        raise GearExecutionError(
            "Refusing to export across groups: this job reads group "
            f"{group_id} but writes to group {destination_group_id}. "
            "The destination must be in the same group as the project "
            "being exported."
        )


def _tag_output(context: GearContext, output_filename: str, gear_name: str) -> None:
    """Tags an output file with the gear name.

    Uses the explicit ``container_type`` path, which resolves the name
    without an API lookup -- outputs do not exist as containers yet at
    gear runtime, so the input-tagging path (``add_file_tags``) does not
    apply.

    Tagging is advisory: a failure here must not discard an export's
    already-written data, so it is logged rather than raised. Note that
    the gear context only writes ``.metadata.json`` when the gear exits
    cleanly, so these tags do not survive a failed run.

    Args:
      context: the gear context
      output_filename: the name of the output file to tag
      gear_name: the tag to apply
    """
    try:
        context.metadata.update_file_metadata(
            output_filename,
            container_type="project",
            tags=[gear_name],
        )
    except Exception as error:  # tagging must not fail the export
        log.warning("Unable to tag output file %s: %s", output_filename, error)


def _write_gatherer_output(
    context: GearContext,
    gatherer: ModuleDataGatherer,
    study_id: str,
    source_id: str,
    run_date: str,
    run_id: str,
    gear_name: str,
) -> None:
    """Writes one gatherer's data content to one or more output files.

    Called immediately after each module finishes gathering (see
    ``main.run``'s ``on_module_gathered`` callback), rather than after all
    modules have gathered, so that an already-completed module's output is
    on disk before a later module has a chance to fail and halt the gear.

    For a gatherer with ``split_by_formver=False`` (default), produces a
    single CSV named ``{study_id}-{source_id}-{module}-{stamp}.csv``.

    For a gatherer with ``split_by_formver=True``, produces one CSV per
    (module, formver) pair, named
    ``{study_id}-{source_id}-{module}-{formver_label}-{stamp}.csv``, for
    example ``adrc-ingest-UDS-v4-2026-05-29.csv``. The formver label is
    normalized via ``formver_label`` (e.g. "1.0" -> "v1", missing ->
    "unknown").

    ``source_id`` names the project this job read, and sits before the
    module rather than after the date because the trailing ``run_id`` is
    optional. If a second optional segment follows the date, a consumer
    cannot tell which of the two it has read.

    ``stamp`` is the run date, plus the caller-supplied ``run_id`` when
    one was given (e.g. ``2026-05-29-20260529T210431``). Both are fixed
    for the whole gear run and passed in rather than computed here. This
    function runs once per module, minutes apart on a large export. If it
    reads the date from the clock at write time, each module gets a
    different stamp, and one run's output splits across several apparent
    runs.

    Args:
      context: the gear context
      gatherer: the ModuleDataGatherer to write output for
      study_id: the study identifier used in output filenames
      source_id: the identifier of the project this job read
      run_date: the run's date, ISO formatted
      run_id: the caller-supplied run identifier, possibly empty
      gear_name: the tag to apply to each output file
    """
    prefix = f"{study_id}-{source_id}"
    stamp = _output_stamp(run_date=run_date, run_id=run_id)
    if gatherer.split_by_formver:
        buckets = gatherer.content_by_formver
        if not buckets:
            log.warning(
                "skipping output for module %s: no data found",
                gatherer.module_name,
            )
            return
        for formver_label_value, content in buckets.items():
            if not content:
                continue
            output_filename = (
                f"{prefix}-{gatherer.module_name}-{formver_label_value}-{stamp}.csv"
            )
            with context.open_output(
                output_filename, mode="w", encoding="utf-8"
            ) as output_file:
                output_file.write(content)
            _tag_output(
                context=context, output_filename=output_filename, gear_name=gear_name
            )
        return

    if not gatherer.content:
        log.warning(
            "skipping output for module %s: no data found",
            gatherer.module_name,
        )
        return

    output_filename = f"{prefix}-{gatherer.module_name}-{stamp}.csv"
    with context.open_output(
        output_filename, mode="w", encoding="utf-8"
    ) as output_file:
        output_file.write(gatherer.content)
    _tag_output(context=context, output_filename=output_filename, gear_name=gear_name)


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
        source_id: str,
        formver_split: bool = False,
        batch_size: int = 100,
        reload_workers: int = 10,
        run_id: str = "",
    ):
        super().__init__(client=client)
        self.__group_id = group_id
        self.__project_name = project_name
        self.__info_paths = info_paths
        self.__modules = modules
        self.__study_id = study_id
        self.__source_id = source_id
        self.__formver_split = formver_split
        self.__batch_size = batch_size
        self.__reload_workers = reload_workers
        self.__run_id = run_id

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
        study_id = options.get("study_id", "adrc").strip()
        formver_split = options.get("formver_split", False)
        batch_size = int(options.get("batch_size", 100))
        reload_workers = int(options.get("reload_workers", 10))
        run_id = options.get("run_id", "").strip()
        source_id = options.get("source_id", "").strip()

        if not group_id:
            raise GearExecutionError("group_id must not be empty")
        if not project_name:
            raise GearExecutionError("project_name must not be empty")
        if not modules:
            raise GearExecutionError("at least one module must be specified")
        if batch_size <= 0:
            raise GearExecutionError("batch_size must be a positive integer")
        if reload_workers <= 0:
            raise GearExecutionError("reload_workers must be a positive integer")

        # Every config value that lands in an output filename, in the order
        # the segments appear in the name.
        _validate_filename_segment(
            name="study_id",
            value=study_id,
            max_length=STUDY_ID_MAX_LENGTH,
            required=True,
        )
        _validate_filename_segment(
            name="source_id",
            value=source_id,
            max_length=SOURCE_ID_MAX_LENGTH,
            required=True,
        )
        # Note: DefaultValues.MODULE_PATTERN in common/keys allows '_' in a
        # module name. Every module NACC currently defines (UDS, FTLD, LBD,
        # ENROLL, MDS, BDS, NP, MLST, CLS) is strictly alphanumeric, and
        # consumers of these filenames anchor on that. If a module name
        # carries an underscore, it fails here, rather than producing a
        # name those consumers reject.
        for module_name in sorted(modules):
            _validate_filename_segment(
                name="module name",
                value=module_name,
                max_length=MODULE_NAME_MAX_LENGTH,
                required=True,
            )
        _validate_filename_segment(
            name="run_id", value=run_id, max_length=RUN_ID_MAX_LENGTH
        )

        return CenterFormExportVisitor(
            client=client,
            group_id=group_id,
            project_name=project_name,
            info_paths=info_paths,
            modules=modules,
            study_id=study_id,
            source_id=source_id,
            formver_split=formver_split,
            batch_size=batch_size,
            reload_workers=reload_workers,
            run_id=run_id,
        )

    def run(self, context: GearContext) -> None:
        """Runs the center form export.

        Refuses the job outright if its destination is in a different
        group than the project it reads (see
        ``_check_destination_group``), before resolving the source or
        gathering anything.

        Otherwise resolves the group/project, then gathers and writes each
        configured module's data in turn: each module's output is written
        to disk as soon as that module finishes gathering, before moving
        on to the next module, so a later module's failure doesn't
        discard an earlier module's already-completed output.

        The date stamping output filenames is computed once here rather
        than per output file, so that every module of one run shares it
        even when the run spans midnight.

        Raises:
          GearExecutionError if the destination is in a different group,
          or if the group or project cannot be found.
        """
        _check_destination_group(
            context=context, proxy=self.proxy, group_id=self.__group_id
        )

        run_date = date.today().isoformat()
        gear_name = self.get_gear_name(context, DEFAULT_GEAR_NAME)

        group = self.proxy.find_group(self.__group_id)
        if not group:
            raise GearExecutionError(f"Group not found: {self.__group_id}")

        project = group.find_project(self.__project_name)
        if not project:
            raise GearExecutionError(
                f"Project not found: {self.__project_name} in group {self.__group_id}"
            )

        subject_ids = [subject.id for subject in project.project.subjects.iter()]
        if not subject_ids:
            log.warning(
                "No subjects found in project %s/%s",
                self.__group_id,
                self.__project_name,
            )
            return

        gatherers = [
            ModuleDataGatherer(
                proxy=self.proxy,
                module_name=module_name,
                info_paths=self.__info_paths,
                split_by_formver=self.__formver_split,
            )
            for module_name in self.__modules
        ]

        run(
            subject_ids=subject_ids,
            gatherers=gatherers,
            on_module_gathered=lambda gatherer: _write_gatherer_output(
                context=context,
                gatherer=gatherer,
                study_id=self.__study_id,
                source_id=self.__source_id,
                run_date=run_date,
                run_id=self.__run_id,
                gear_name=gear_name,
            ),
            batch_size=self.__batch_size,
            reload_workers=self.__reload_workers,
        )


def main():
    """Main method for Center Form Export."""
    GearEngine().create_with_parameter_store().run(gear_type=CenterFormExportVisitor)


if __name__ == "__main__":
    main()
