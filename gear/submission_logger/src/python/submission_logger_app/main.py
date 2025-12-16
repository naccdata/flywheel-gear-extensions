"""Defines Submission Logger.

The Submission Logger processes exactly one input file per gear
execution, extracting visit information and creating submit events for
each visit found in that single file.
"""

import logging
from pathlib import Path
from typing import Optional, Protocol

from configs.ingest_configs import FormProjectConfigs, ModuleConfigs
from error_logging.error_logger import ErrorLogTemplate
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logging import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from inputs.csv_reader import AggregateCSVVisitor, read_csv
from metrics.processing_metrics import ProcessingMetrics
from outputs.error_writer import ListErrorWriter

from submission_logger_app.file_visit_annotator import FileVisitAnnotator
from submission_logger_app.metrics_tracking_visitor import MetricsTrackingVisitor
from submission_logger_app.qc_status_log_creator import QCStatusLogCreator
from submission_logger_app.qc_status_log_csv_visitor import QCStatusLogCSVVisitor

log = logging.getLogger(__name__)


class SubmissionLoggerError(Exception):
    """Base exception for submission logger processing errors."""

    pass


class ConfigurationError(SubmissionLoggerError):
    """Raised when there are configuration-related errors."""

    pass


class FileProcessingError(SubmissionLoggerError):
    """Raised when there are file processing errors."""

    pass


class FileInputProtocol(Protocol):
    """Protocol for file input objects."""

    @property
    def filename(self) -> str:
        """The filename of the input file."""
        ...

    @property
    def filepath(self) -> str:
        """The full path to the input file."""
        ...

    def validate_file_extension(self, accepted_extensions: list[str]) -> str | None:
        """Validate if the file has one of the given extensions."""
        ...

    def get_parent_project(self, proxy):
        """Get the parent project for this file."""
        ...


# Global metrics instance for tracking across function calls
_processing_metrics = ProcessingMetrics()


def _process_csv_form_data(
    *,
    file_input: FileInputProtocol,
    event_logger: VisitEventLogger,
    gear_name: str,
    proxy: FlywheelProxy,
    timestamp,
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
        error_msg = f"No module configurations found for module: {module}"
        raise ConfigurationError(error_msg)

    # Get project information with error handling
    try:
        parent_project = file_input.get_parent_project(proxy)
        project = ProjectAdaptor(project=parent_project, proxy=proxy)
    except (AttributeError, KeyError, ValueError) as e:
        error_msg = f"Failed to get project information: {e!s}"
        raise ConfigurationError(error_msg) from e

    # Get center and project labels
    center_label = project.group
    project_label = project.label

    # Create event logging visitor for submit events with error handling
    try:
        event_visitor = CSVLoggingVisitor(
            center_label=center_label,
            project_label=project_label,
            gear_name=gear_name,
            event_logger=event_logger,
            module_configs=module_configs,
            error_writer=error_writer,
            timestamp=timestamp,
            action="submit",  # Key difference - this creates submit events
            datatype="form",
        )
    except (TypeError, ValueError, AttributeError) as e:
        error_msg = f"Failed to create event logging visitor: {e!s}"
        raise ConfigurationError(error_msg) from e

    # Create QC status log creator and visitor with error handling
    try:
        error_log_template = (
            module_configs.errorlog_template
            if module_configs.errorlog_template
            else ErrorLogTemplate()
        )
        visit_annotator = FileVisitAnnotator(project)
        qc_log_creator = QCStatusLogCreator(error_log_template, visit_annotator)
        qc_visitor = QCStatusLogCSVVisitor(
            module_configs=module_configs,
            project=project,
            qc_log_creator=qc_log_creator,
            gear_name=gear_name,
            error_writer=error_writer,
        )
    except (TypeError, ValueError, AttributeError) as e:
        error_msg = f"Failed to create QC status log visitor: {e!s}"
        raise ConfigurationError(error_msg) from e

    # Aggregate both visitors
    csv_visitor = AggregateCSVVisitor([event_visitor, qc_visitor])

    # Wrap with metrics tracking visitor
    metrics_visitor = MetricsTrackingVisitor(csv_visitor, _processing_metrics)

    # Process CSV file using existing infrastructure with comprehensive error
    # handling
    try:
        with open(file_input.filepath, "r", encoding="utf-8") as input_file:
            success = read_csv(
                input_file=input_file,
                error_writer=error_writer,
                visitor=metrics_visitor,
                clear_errors=False,
                preserve_case=True,
            )

            # Metrics are now tracked automatically by MetricsTrackingVisitor
            if not success:
                _processing_metrics.record_error("csv-processing-error")

            return success

    except UnicodeDecodeError as e:
        error_msg = f"File encoding error - file must be UTF-8 compliant: {e!s}"
        raise FileProcessingError(error_msg) from e
    except FileNotFoundError as e:
        error_msg = f"Input file not found: {e!s}"
        raise FileProcessingError(error_msg) from e
    except PermissionError as e:
        error_msg = f"Permission denied accessing file: {e!s}"
        raise FileProcessingError(error_msg) from e
    except OSError as e:
        error_msg = f"File system error during CSV processing: {e!s}"
        raise FileProcessingError(error_msg) from e


def _process_csv_file(
    *,
    file_input: FileInputProtocol,
    event_logger: VisitEventLogger,
    gear_name: str,
    proxy: FlywheelProxy,
    timestamp,
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
        timestamp: the timestamp for processing
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
        timestamp=timestamp,
        error_writer=error_writer,
        form_project_configs=form_project_configs,
        module=module,
    )


def run(
    *,
    file_input: FileInputProtocol,
    event_logger: VisitEventLogger,
    gear_name: str,
    proxy: FlywheelProxy,
    timestamp,
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

    # Reset metrics for this processing run
    global _processing_metrics
    _processing_metrics = ProcessingMetrics()
    _processing_metrics.start_processing()

    success = False

    try:
        # Validate file exists and is accessible
        file_path = Path(file_input.filepath)
        if not file_path.exists():
            error_msg = f"Input file does not exist: {file_input.filepath}"
            raise FileProcessingError(error_msg)

        if not file_path.is_file():
            error_msg = f"Input path is not a file: {file_input.filepath}"
            raise FileProcessingError(error_msg)

        # Check file size (warn if empty, but don't fail)
        if file_path.stat().st_size == 0:
            log.warning(f"Input file is empty: {file_input.filename}")
            # Continue processing - empty file is handled by CSV reader

        # Dispatch to appropriate processor based on file type
        if file_input.validate_file_extension(["csv"]) is not None:
            # CSV file requires form configuration
            if not form_project_configs or not module:
                error_msg = (
                    "CSV file requires form_configs_file and module configuration"
                )
                raise ConfigurationError(error_msg)

            try:
                success = _process_csv_file(
                    file_input=file_input,
                    event_logger=event_logger,
                    gear_name=gear_name,
                    proxy=proxy,
                    timestamp=timestamp,
                    error_writer=error_writer,
                    form_project_configs=form_project_configs,
                    module=module,
                )
            except Exception as e:
                # Log the error but don't re-raise - let processing complete gracefully
                error_msg = f"Unexpected error during CSV file processing: {e!s}"
                log.error(error_msg)
                success = False

        # TODO: Add support for other single file types here
        # elif file_input.validate_file_extension(["json"]) is not None:
        #     success = _process_json_file(...)
        # elif file_input.validate_file_extension(["xlsx"]) is not None:
        #     success = _process_excel_file(...)
        else:
            error_msg = f"Unsupported file type: {file_input.filename}"
            raise FileProcessingError(error_msg)

    except OSError as e:
        # File system related errors
        error_msg = f"File system error in submission logger: {e!s}"
        raise FileProcessingError(error_msg) from e

    finally:
        # Mark end of processing and log summary for operational monitoring
        _processing_metrics.end_processing()
        _processing_metrics.log_summary()

        if success:
            log.info("File processing completed successfully")
        else:
            log.warning(
                "File processing completed with errors - check error logs for details"
            )

    return success
