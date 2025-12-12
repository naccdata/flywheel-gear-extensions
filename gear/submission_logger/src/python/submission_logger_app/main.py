"""Defines Submission Logger."""

import logging
from typing import Optional

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logging import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from inputs.csv_reader import read_csv
from outputs.error_writer import ListErrorWriter

log = logging.getLogger(__name__)


def _process_csv_form_data(
    *,
    file_input: InputFileWrapper,
    event_logger: VisitEventLogger,
    gear_name: str,
    proxy: FlywheelProxy,
    context: GearToolkitContext,
    error_writer: ListErrorWriter,
    form_project_configs: FormProjectConfigs,
    module: str,
) -> bool:
    """Process CSV file as form data using CSVLoggingVisitor.

    Args:
        file_input: the input file wrapper
        event_logger: the visit event logger
        gear_name: the gear name
        proxy: the proxy for the Flywheel instance
        context: the gear execution context
        error_writer: the error writer for tracking processing errors
        form_project_configs: the form project configurations
        module: the module name for processing

    Returns:
        True if processing was successful, False otherwise
    """
    log.info("Processing CSV as form data with CSVLoggingVisitor")

    # Get module configurations
    module_configs: ModuleConfigs = form_project_configs.module_configs.get(module)  # type: ignore
    if not module_configs:
        log.error(f"No module configurations found for module: {module}")
        return False

    # Get project information
    parent_project = file_input.get_parent_project(proxy)
    project = ProjectAdaptor(project=parent_project, proxy=proxy)

    # Get center and project labels
    center_label = project.group
    project_label = project.label

    # Create CSVLoggingVisitor for submit event creation
    csv_visitor = CSVLoggingVisitor(
        center_label=center_label,
        project_label=project_label,
        gear_name=gear_name,
        event_logger=event_logger,
        module_configs=module_configs,
        error_writer=error_writer,
        timestamp=file_input.file_entry(context).created,
        action="submit",  # Key difference - this creates submit events
        datatype="form",
    )

    # Process CSV file using existing infrastructure
    with open(file_input.filepath, "r", encoding="utf-8") as input_file:
        success = read_csv(
            input_file=input_file,
            error_writer=error_writer,
            visitor=csv_visitor,
            clear_errors=False,
            preserve_case=True,
        )

    return success


def _process_csv_file(
    *,
    file_input: InputFileWrapper,
    event_logger: VisitEventLogger,
    gear_name: str,
    proxy: FlywheelProxy,
    context: GearToolkitContext,
    error_writer: ListErrorWriter,
    form_project_configs: FormProjectConfigs,
    module: str,
) -> bool:
    """Process CSV file as form data using CSVLoggingVisitor.

    Args:
        file_input: the input file wrapper
        event_logger: the visit event logger
        gear_name: the gear name
        proxy: the proxy for the Flywheel instance
        context: the gear execution context
        error_writer: the error writer for tracking processing errors
        form_project_configs: the form project configurations
        module: the module name for processing

    Returns:
        True if processing was successful, False otherwise
    """
    log.info("CSV file detected, processing as form data")

    return _process_csv_form_data(
        file_input=file_input,
        event_logger=event_logger,
        gear_name=gear_name,
        proxy=proxy,
        context=context,
        error_writer=error_writer,
        form_project_configs=form_project_configs,
        module=module,
    )


def run(
    *,
    file_input: InputFileWrapper,
    event_logger: VisitEventLogger,
    gear_name: str,
    proxy: FlywheelProxy,
    context: GearToolkitContext,
    error_writer: ListErrorWriter,
    form_project_configs: Optional[FormProjectConfigs],
    module: Optional[str],
) -> bool:
    """Runs the Submission Logger process.

    Args:
        file_input: the input file wrapper
        event_logger: the visit event logger
        gear_name: the gear name
        proxy: the proxy for the Flywheel instance
        context: the gear execution context
        error_writer: the error writer for tracking processing errors
        form_project_configs: the form project configurations
        module: the module name for processing

    Returns:
        True if processing was successful, False otherwise
    """
    log.info(f"Starting submission logger for file: {file_input.filename}")

    # Dispatch to appropriate processor based on file type
    if file_input.validate_file_extension(["csv"]):
        # CSV files require form configuration
        if not form_project_configs or not module:
            log.error("CSV files require form_configs_file and module configuration")
            return False

        success = _process_csv_file(
            file_input=file_input,
            event_logger=event_logger,
            gear_name=gear_name,
            proxy=proxy,
            context=context,
            error_writer=error_writer,
            form_project_configs=form_project_configs,
            module=module,
        )
    # TODO: Add support for other file types here
    # elif file_input.validate_file_extension(["json"]):
    #     success = _process_json_file(...)
    # elif file_input.validate_file_extension(["xlsx"]):
    #     success = _process_excel_file(...)
    else:
        log.warning(f"Unsupported file type: {file_input.filename}")
        return False

    if success:
        log.info("File processing completed successfully")
    else:
        log.warning("File processing completed with errors")

    return success
