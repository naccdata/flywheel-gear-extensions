"""Defines Form Screening."""

import logging
import os
from io import StringIO
from typing import Any, Dict, List, Optional

from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from fw_gear import GearContext
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from gear_execution.gear_trigger import (
    CredentialGearConfigs,
    GearInfo,
    set_gear_inputs,
    trigger_gear,
)
from inputs.csv_reader import read_csv
from jobs.job_poll import JobPoll
from keys.keys import SysErrorCodes
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import (
    empty_file_error,
    non_utf8_file_error,
    preprocessing_error,
)

from form_screening_app.format import CSVFormatterVisitor

log = logging.getLogger(__name__)


class FormSchedulerGearConfigs(CredentialGearConfigs):
    """Form Scheduler-specific gear configs."""

    source_email: str
    portal_url_path: str


def save_output(
    context: GearContext,
    outfilename: str,
    contents: str,
    tags: Optional[List[str]] = None,
    info: Optional[Dict[str, Any]] = None,
):
    """Saves the output file and add tags/metadata if any.

    Args:
        context: gear context
        outfilename: output file name
        contents: output contents
        tags (optional): tag(s) to add to output file. Defaults to None.
        info (optional): custom info to add to output file. Defaults to None.
    """
    log.info("Saving file %s in UTF-8", outfilename)
    out_file_path = os.path.join(context.output_dir, outfilename)
    with context.open_output(out_file_path, mode="w", encoding="utf-8") as out_file:
        out_file.write(contents)

    if info:
        qc_status = {"validation": {"state": "PASS", "data": []}}
        updated_info = context.metadata.add_gear_info("qc", outfilename, **qc_status)
        info["qc"] = updated_info["qc"]

    if tags or info:
        context.metadata.update_file_metadata(
            file_=outfilename,
            container_type=context.config.destination["type"],
            tags=tags,
            info=info,
        )


def get_scheduler_gear_inputs(
    scheduler_gear: GearInfo, project: ProjectAdaptor
) -> Dict[str, FileEntry]:
    """Get the input files for the form scheduler gear.

    Args:
        scheduler_gear: form scheduler gear info
        project: Flywheel project container

    Returns:
        Dict[str, FileEntry]: scheduler gear inputs
    """
    gear_input_info = scheduler_gear.get_inputs_by_file_locator_type(locators=["fixed"])

    gear_inputs: Dict[str, FileEntry] = {}
    # set gear inputs of file locator type fixed
    # these are the project level files with fixed filename specified in the configs
    if gear_input_info and "fixed" in gear_input_info:
        set_gear_inputs(
            project=project,
            gear_name=scheduler_gear.gear_name,
            locator="fixed",
            gear_inputs_list=gear_input_info["fixed"],
            gear_inputs=gear_inputs,
        )

    return gear_inputs


def trigger_scheduler_gear(
    *, proxy: FlywheelProxy, project: ProjectAdaptor, scheduler_gear: GearInfo
):
    """Trigger the form-scheduler gear if it's not already running on the given
    project.

    Args:
        proxy: the proxy for the Flywheel instance
        project: Flywheel project container
        scheduler_gear: form-scheduler gear info
    """
    # check if the scheduler gear is pending/running
    log.info(f"Checking status of {scheduler_gear.gear_name}")

    search_str = JobPoll.generate_search_string(
        project_ids_list=[project.id],
        gears_list=[scheduler_gear.gear_name],
        states_list=["running", "pending"],
    )

    if proxy.find_job(search_str):
        log.info(f"{scheduler_gear.gear_name} gear already running, exiting")
        return None

    # otherwise invoke the gear
    log.info(f"No {scheduler_gear.gear_name} gears running, triggering")
    trigger_gear(
        proxy=proxy,
        gear_name=scheduler_gear.gear_name,
        config=scheduler_gear.configs.model_dump(),
        inputs=get_scheduler_gear_inputs(
            scheduler_gear=scheduler_gear, project=project
        ),
        destination=project.project,
    )


def run(
    *,
    proxy: FlywheelProxy,
    context: GearContext,
    file_input: InputFileWrapper,
    accepted_modules: List[str],
    queue_tags: List[str],
    scheduler_gear: GearInfo,
    format_and_tag: bool,
    gear_name: str,
) -> Optional[ListErrorWriter]:
    """Runs the form screening process. Checks that the file suffix matches any
    accepted modules, if the suffix does not match, report an error.
        If format_and_tag=True (only supported for CSVs):
            formats the input file:
                removes any REDCap specific ID columns,
                converts column headers to lowercase,
                removes BOM characters and saves the file in UTF-8.
            tags the file with the specified queue_tags
        Else:
            check whether the input file is already tagged with one or more queue_tags

        If the conditions met, trigger form-scheduler gear if it's not already running.

    Args:
        proxy: the proxy for the Flywheel instance
        file_input: the InputFileWrapper representing the file to
            potentially queue
        accepted_modules: list of accepted modules (case-insensitive)
        queue_tags: list of tags to add to the file or check whether already tagged
        scheduler_gear: GearInfo of the scheduler gear to trigger
        format_and_tag: if True format input file and add queue_tags,
                        else check whether the file is already tagged with queue_tags
        gear_name: The gear name

    Returns:
        ListErrorWriter(optional): If file didn't pass screening checks
    """

    file = proxy.get_file(file_input.file_id)
    project = ProjectAdaptor(
        project=file_input.get_parent_project(proxy=proxy, file=file), proxy=proxy
    )

    if not format_and_tag:
        # check whether the input file has pipeline trigger tag(s)
        # tag can be already removed if form-scheduler process the file
        #  before form-screening move to running status, so just log warning
        if not (set(file.tags) & set(queue_tags)):
            log.warning(
                f"Input file tags {file.tags} does not contain "
                f"the expected pipeline trigger tags {queue_tags}"
            )
            return None

        # if matching tags present start form-scheduler gear if it's not already running
        trigger_scheduler_gear(
            proxy=proxy, project=project, scheduler_gear=scheduler_gear
        )
        return None

    file_type = file_input.validate_file_extension(accepted_extensions=["csv"])
    if not file_type:
        raise GearExecutionError(
            f"Unsupported input file type {file_input.file_type}, expected CSV file"
        )

    module = file_input.basename.split("-")[-1]
    error_writer = ListErrorWriter(
        container_id=file_input.file_id, fw_path=proxy.get_lookup_path(file)
    )

    if module.lower() not in accepted_modules:
        log.error(f"Module suffix {module} not in the list of accepted modules")
        error_writer.write(
            preprocessing_error(
                field=FieldNames.MODULE,
                value=module,
                line=0,
                error_code=SysErrorCodes.INVALID_MODULE,
            )
        )

        return error_writer

    if proxy.dry_run:
        log.info(
            "DRY RUN: file passes prescreening, would format the file and add tags %s",
            queue_tags,
        )
        return None

    out_stream = StringIO()
    formatter_visitor = CSVFormatterVisitor(
        output_stream=out_stream, error_writer=error_writer
    )

    # open file using utf-8-sig to treat the BOM as metadata (if present)
    success = False
    try:
        with open(file_input.filepath, mode="r", encoding="utf-8-sig") as csv_file:
            success = read_csv(
                input_file=csv_file,
                error_writer=error_writer,
                visitor=formatter_visitor,
            )
    except UnicodeDecodeError as e:
        log.error(f"Cannot read non UTF-8 compliant file: {e}")
        error_writer.write(non_utf8_file_error())

    if not success:
        return error_writer

    contents = out_stream.getvalue()
    if not len(contents) > 0:
        log.warning(
            "Contents empty, will not write output file %s", file_input.filename
        )
        error_writer.write(empty_file_error())
        return error_writer

    queue_tags.append(gear_name)

    # save the original uploader's ID in custom info (for email notification)
    info: Dict[str, Any] = {"uploader": file.origin.id}

    # save output file and add tags/metadata
    save_output(
        context=context,
        contents=contents,
        outfilename=file_input.filename,
        tags=queue_tags,
        info=info,
    )

    trigger_scheduler_gear(proxy=proxy, project=project, scheduler_gear=scheduler_gear)
    return None
