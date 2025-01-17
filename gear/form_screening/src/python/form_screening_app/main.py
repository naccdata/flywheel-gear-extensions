"""Defines Form Screening."""
import logging
from typing import List

from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import InputFileWrapper
from gear_execution.gear_trigger import GearInfo, trigger_gear
from jobs.job_poll import JobPoll
from keys.keys import FieldNames, SysErrorCodes
from outputs.errors import ListErrorWriter, preprocessing_error

log = logging.getLogger(__name__)


def run(*,
        proxy: FlywheelProxy,
        context: GearToolkitContext,
        file_input: InputFileWrapper,
        accepted_modules: List[str],
        queue_tags: List[str],
        scheduler_gear: GearInfo,
        error_writer: ListErrorWriter) -> bool:
    """Runs the form screening process. Checks that the file suffix matches any
    accepted modules; if so, tags the file with the specified tags, and run the
    form-scheduler gear if it's not already running. If the suffix
    does not match, report an error.

    Args:
        proxy: the proxy for the Flywheel instance
        file_input: The InputFileWrapper representing the file to
            potentially queue
        accepted_modules: List of accepted modules (case-insensitive)
        queue_tags: List of tags to add if the file passes prescreening
        scheduler_gear: GearInfo of the scheduler gear to trigger
        error_writer: The error writer
    Returns:
        Whether or not the file passed screening checks
    """
    module = file_input.basename.split('-')[-1]

    if module.lower() not in accepted_modules:
        log.error(f"Unallowed module suffix: {module}")
        error_writer.write(
            preprocessing_error(field=FieldNames.MODULE,
                                value=module,
                                line=0,
                                error_code=SysErrorCodes.INVALID_MODULE))
        return False

    file = proxy.get_file(file_input.file_id)
    if proxy.dry_run:
        log.info("DRY RUN: file passes prescreening, would have added" +
                 f"{queue_tags}")
    else:
        # add the specified tags
        log.info(f"Adding the following tags to file: {queue_tags}")
        context.metadata.add_file_tags(file_input.file_input,
                                       tags=queue_tags)

    # check if the scheduler gear is pending/running
    project_id = file.parents.project
    gear_name = scheduler_gear.gear_name
    log.info(f"Checking status of {gear_name}")

    search_str = JobPoll.generate_search_string(
        project_ids_list=[project_id],
        gears_list=[scheduler_gear.gear_name],
        states_list=['running', 'pending'])

    if proxy.find_job(search_str):
        log.info("Scheduler gear already running, exiting")
        return True

    if proxy.dry_run:
        log.info("DRY RUN: Would trigger scheduler gear")
        return True

    log.info(f"No {gear_name} gears running, triggering")
    # otherwise invoke the gear
    trigger_gear(proxy=proxy,
                 gear_name=gear_name,
                 config=scheduler_gear.configs.model_dump(),
                 destination=proxy.get_project_by_id(project_id))

    return True
