"""Defines Form Screening."""
import logging
from io import StringIO
from typing import Any, Dict, List

from flywheel import FileEntry, FileSpec
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import GearExecutionError, InputFileWrapper
from gear_execution.gear_trigger import GearConfigs, GearInfo, trigger_gear
from inputs.csv_reader import read_csv
from jobs.job_poll import JobPoll
from keys.keys import FieldNames, SysErrorCodes
from outputs.errors import ListErrorWriter, preprocessing_error

from form_screening_app.format import CSVFormatterVisitor

log = logging.getLogger(__name__)


class FormSchedulerGearConfigs(GearConfigs):
    """Form Scheduler-specific gear configs."""
    submission_pipeline: str
    accepted_modules: str
    queue_tags: str
    source_email: str
    portal_url_path: str


def run(*, proxy: FlywheelProxy, context: GearToolkitContext,
        file_input: InputFileWrapper, accepted_modules: List[str],
        queue_tags: List[str], scheduler_gear: GearInfo):
    """Runs the form screening process. Checks that the file suffix matches any
    accepted modules; if so, tags the file with the specified tags, and run the
    form-scheduler gear if it's not already running. If the suffix does not
    match, report an error.

    Also formats the input CSV:
    removes any REDCap specific ID columns,
    converts column headers to lowercase,
    removes BOM characters and saves the file in UTF-8.

    Args:
        proxy: the proxy for the Flywheel instance
        file_input: The InputFileWrapper representing the file to
            potentially queue
        accepted_modules: List of accepted modules (case-insensitive)
        queue_tags: List of tags to add if the file passes prescreening
        scheduler_gear: GearInfo of the scheduler gear to trigger
    """
    module = file_input.basename.split('-')[-1]

    file = proxy.get_file(file_input.file_id)
    error_writer = ListErrorWriter(container_id=file_input.file_id,
                                   fw_path=proxy.get_lookup_path(file))

    if module.lower() not in accepted_modules:
        log.error(f"Un-accepted module suffix: {module}")
        error_writer.write(
            preprocessing_error(field=FieldNames.MODULE,
                                value=module,
                                line=0,
                                error_code=SysErrorCodes.INVALID_MODULE))

        context.metadata.add_qc_result(file_input.file_input,
                                       name='validation',
                                       state='FAIL',
                                       data=error_writer.errors())
        return

    if proxy.dry_run:
        log.info(
            "DRY RUN: file passes prescreening, would format the file and add tags %s",
            queue_tags)
        return

    project = file_input.get_parent_project(proxy=proxy)
    out_stream = StringIO()
    formatter_visitor = CSVFormatterVisitor(output_stream=out_stream)

    # open file using utf-8-sig to treat the BOM as metadata (if present)
    with open(file_input.filepath, mode='r', encoding='utf-8-sig') as csv_file:
        success = read_csv(input_file=csv_file,
                           error_writer=error_writer,
                           visitor=formatter_visitor)

        if not success:
            context.metadata.add_qc_result(file_input.file_input,
                                           name='validation',
                                           state='FAIL',
                                           data=error_writer.errors())
            return

    gear_name = context.manifest.get('name', 'form-screening')
    queue_tags.append(gear_name)

    # save the original uploader's ID in custom info (for email notification)
    file = file.reload()
    log.info("Original file version: %s", file.version)
    info: Dict[str, Any] = {
        "uploader": file.origin.id,
        "qc": {
            gear_name: {
                "validation": {
                    "state": 'PASS',
                    "data": {}
                }
            }
        }
    }

    contents = out_stream.getvalue()
    if len(contents) > 0:
        log.info("Saving file %s in UTF-8", file_input.filename)
        file_spec = FileSpec(name=file_input.filename,
                             contents=str.encode(contents).decode(),
                             content_type='text/csv',
                             size=len(contents))

        # Note: use project.upload_file() instead of context.open_output()
        # Adding the tags/info didn't work with context.open_output()
        # It adds the tags/info to original version of the file instead of new version
        # even after reloading project and file
        try:
            updated_file: FileEntry = project.upload_file(file_spec)[0]
            log.info("New file version: %s", updated_file.version)
            updated_file.add_tags(tags=queue_tags)
            updated_file.update_info(info)
            log.info(f"Added the following tags to input file: {queue_tags}")
        except ApiException as error:
            raise GearExecutionError(
                f'Failed to update file {file_input.filename}: {error}'
            ) from error
    else:
        log.info("Contents empty, will not write output file %s",
                 file_input.filename)
        return

    # check if the scheduler gear is pending/running
    log.info(f"Checking status of {scheduler_gear.gear_name}")

    search_str = JobPoll.generate_search_string(
        project_ids_list=[project.id],
        gears_list=[scheduler_gear.gear_name],
        states_list=['running', 'pending'])

    if proxy.find_job(search_str):
        log.info("Scheduler gear already running, exiting")
        return

    log.info(f"No {scheduler_gear.gear_name} gears running, triggering")
    # otherwise invoke the gear
    trigger_gear(proxy=proxy,
                 gear_name=scheduler_gear.gear_name,
                 config=scheduler_gear.configs.model_dump(),
                 destination=project)

    return
