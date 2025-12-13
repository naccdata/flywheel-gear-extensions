"""Defines Submission Logger.

The Submission Logger processes exactly one input file per gear
execution, extracting visit information and creating submit events for
each visit found in that single file.
"""

import logging
from pathlib import Path
from typing import Optional

from configs.ingest_configs import ErrorLogTemplate, FormProjectConfigs, ModuleConfigs
from event_logging.csv_logging_visitor import CSVLoggingVisitor
from event_logging.event_logging import VisitEventLogger
from flywheel_adaptor.flywheel_proxy import FlywheelProxy, ProjectAdaptor
from flywheel_gear_toolkit import GearToolkitContext
from gear_execution.gear_execution import InputFileWrapper
from inputs.csv_reader import AggregateCSVVisitor, read_csv
from outputs.error_writer import ListErrorWriter
from outputs.errors import malformed_file_error, non_utf8_file_error, system_error

from submission_logger_app.file_visit_annotator import FileVisitAnnotator
from submission_logger_app.metrics_tracking_visitor import MetricsTrackingVisitor
from submission_logger_app.qc_status_log_creator import QCStatusLogCreator
from submission_logger_app.qc_status_log_csv_visitor import QCStatusLogCSVVisitor

log = logging.getLogger(__name__)


class ProcessingMetrics:
    """Tracks processing metrics for operational monitoring.

    Focuses on visit-level metrics since the gear processes exactly one
    file per execution. Tracks visits found, events created, and QC logs
    created for the single input file being processed.
    """

    def __init__(self):
        self.visits_found = 0
        self.visits_processed_successfully = 0
        self.visits_failed = 0
        self.events_created = 0
        self.events_failed = 0
        self.qc_logs_created = 0
        self.qc_logs_failed = 0
        self.errors_encountered = 0
        self.error_types = {}
        self.processing_start_time = None
        self.processing_end_time = None

    def start_processing(self):
        """Mark the start of single-file processing."""
        from datetime import datetime

        self.processing_start_time = datetime.now()
        log.info("Starting submission logger processing for single input file")

    def end_processing(self):
        """Mark the end of single-file processing."""
        from datetime import datetime

        self.processing_end_time = datetime.now()

    def get_processing_duration(self) -> float:
        """Get processing duration in seconds for the single input file."""
        if self.processing_start_time and self.processing_end_time:
            return (
                self.processing_end_time - self.processing_start_time
            ).total_seconds()
        return 0.0

    def increment_visits_found(self, count: int = 1):
        """Increment the count of visits found in the input file."""
        self.visits_found += count
        log.debug(f"Total visits found in input file: {self.visits_found}")

    def increment_visits_processed_successfully(self, count: int = 1):
        """Increment the count of visits processed successfully."""
        self.visits_processed_successfully += count
        log.debug(
            f"Visits processed successfully: {self.visits_processed_successfully}"
        )

    def increment_visits_failed(self, count: int = 1):
        """Increment the count of visits that failed processing."""
        self.visits_failed += count
        log.debug(f"Visits failed: {self.visits_failed}")

    def increment_events_created(self, count: int = 1):
        """Increment the count of events created."""
        self.events_created += count
        log.debug(f"Events created: {self.events_created}")

    def increment_events_failed(self, count: int = 1):
        """Increment the count of events that failed to be created."""
        self.events_failed += count
        log.debug(f"Events failed: {self.events_failed}")

    def increment_qc_logs_created(self, count: int = 1):
        """Increment the count of QC logs created."""
        self.qc_logs_created += count
        log.debug(f"QC logs created: {self.qc_logs_created}")

    def increment_qc_logs_failed(self, count: int = 1):
        """Increment the count of QC logs that failed to be created."""
        self.qc_logs_failed += count
        log.debug(f"QC logs failed: {self.qc_logs_failed}")

    def record_error(self, error_type: str):
        """Record an error by type."""
        self.errors_encountered += 1
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
        log.debug(
            f"Error recorded: {error_type} (total errors: {self.errors_encountered})"
        )

    def log_summary(self):
        """Log processing summary statistics for the single input file."""
        duration = self.get_processing_duration()

        log.info("=" * 60)
        log.info("SUBMISSION LOGGER PROCESSING SUMMARY")
        log.info("=" * 60)
        log.info(f"Single File Processing Duration: {duration:.2f} seconds")
        log.info(f"Visits Found in Input File: {self.visits_found}")
        log.info(f"Visits Processed Successfully: {self.visits_processed_successfully}")
        log.info(f"Visits Failed: {self.visits_failed}")
        log.info(f"Submit Events Created: {self.events_created}")
        log.info(f"Submit Events Failed: {self.events_failed}")
        log.info(f"QC Status Logs Created: {self.qc_logs_created}")
        log.info(f"QC Status Logs Failed: {self.qc_logs_failed}")
        log.info(f"Total Errors Encountered: {self.errors_encountered}")

        if self.error_types:
            log.info("Error Breakdown by Type:")
            for error_type, count in sorted(self.error_types.items()):
                log.info(f"  {error_type}: {count}")

        # Calculate success rates for visits in the single input file
        if self.visits_found > 0:
            success_rate = (
                self.visits_processed_successfully / self.visits_found
            ) * 100
            log.info(f"Visit Processing Success Rate: {success_rate:.1f}%")

        if self.events_created + self.events_failed > 0:
            event_success_rate = (
                self.events_created / (self.events_created + self.events_failed)
            ) * 100
            log.info(f"Event Creation Success Rate: {event_success_rate:.1f}%")

        if self.qc_logs_created + self.qc_logs_failed > 0:
            qc_success_rate = (
                self.qc_logs_created / (self.qc_logs_created + self.qc_logs_failed)
            ) * 100
            log.info(f"QC Log Creation Success Rate: {qc_success_rate:.1f}%")

        log.info("=" * 60)

    def get_metrics_dict(self) -> dict:
        """Return metrics as a dictionary for programmatic access.

        Focuses on visit-level metrics for the single input file
        processed per gear execution.
        """
        return {
            "processing_duration_seconds": self.get_processing_duration(),
            "visits_found": self.visits_found,
            "visits_processed_successfully": self.visits_processed_successfully,
            "visits_failed": self.visits_failed,
            "events_created": self.events_created,
            "events_failed": self.events_failed,
            "qc_logs_created": self.qc_logs_created,
            "qc_logs_failed": self.qc_logs_failed,
            "errors_encountered": self.errors_encountered,
            "error_types": self.error_types.copy(),
            "visit_success_rate": (
                (self.visits_processed_successfully / self.visits_found * 100)
                if self.visits_found > 0
                else 0.0
            ),
            "event_success_rate": (
                (self.events_created / (self.events_created + self.events_failed) * 100)
                if (self.events_created + self.events_failed) > 0
                else 0.0
            ),
            "qc_log_success_rate": (
                (
                    self.qc_logs_created
                    / (self.qc_logs_created + self.qc_logs_failed)
                    * 100
                )
                if (self.qc_logs_created + self.qc_logs_failed) > 0
                else 0.0
            ),
        }


# Global metrics instance for tracking across function calls
_processing_metrics = ProcessingMetrics()


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
    misc_errors: list,
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

    try:
        # Get module configurations
        module_configs: ModuleConfigs = form_project_configs.module_configs.get(module)  # type: ignore
        if not module_configs:
            error_msg = f"No module configurations found for module: {module}"
            log.error(error_msg)
            _processing_metrics.record_error("configuration-error")
            return False

        # Get project information with error handling
        try:
            parent_project = file_input.get_parent_project(proxy)
            project = ProjectAdaptor(project=parent_project, proxy=proxy)
        except Exception as e:
            error_msg = f"Failed to get project information: {e!s}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("project-access-error")
            return False

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
                timestamp=file_input.file_entry(context).created,
                action="submit",  # Key difference - this creates submit events
                datatype="form",
            )
        except Exception as e:
            error_msg = f"Failed to create event logging visitor: {e!s}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("visitor-creation-error")
            return False

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
        except Exception as e:
            error_msg = f"Failed to create QC status log visitor: {e!s}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("qc-visitor-creation-error")
            return False

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
            log.error(error_msg)
            misc_errors.append(non_utf8_file_error())
            _processing_metrics.record_error("encoding-error")
            return False
        except FileNotFoundError as e:
            error_msg = f"Input file not found: {e!s}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("file-not-found-error")
            return False
        except PermissionError as e:
            error_msg = f"Permission denied accessing file: {e!s}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("permission-error")
            return False
        except Exception as e:
            error_msg = f"Unexpected error during CSV processing: {e!s}"
            log.error(error_msg)
            misc_errors.append(malformed_file_error(str(e)))
            _processing_metrics.record_error("unexpected-processing-error")
            return False

    except Exception as e:
        # Catch-all for any other unexpected errors
        error_msg = f"Critical error in CSV form data processing: {e!s}"
        log.error(error_msg)
        misc_errors.append(system_error(error_msg))
        _processing_metrics.record_error("critical-error")
        return False


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
    misc_errors: list,
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
        misc_errors=misc_errors,
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

    # Reset metrics for this processing run
    global _processing_metrics
    _processing_metrics = ProcessingMetrics()
    _processing_metrics.start_processing()

    success = False
    misc_errors = []  # For system errors that can't be associated with specific visits

    try:
        # Validate file exists and is accessible
        file_path = Path(file_input.filepath)
        if not file_path.exists():
            error_msg = f"Input file does not exist: {file_input.filepath}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("file-not-found")
            return False

        if not file_path.is_file():
            error_msg = f"Input path is not a file: {file_input.filepath}"
            log.error(error_msg)
            misc_errors.append(system_error(error_msg))
            _processing_metrics.record_error("invalid-file-path")
            return False

        # Check file size (warn if empty, but don't fail)
        if file_path.stat().st_size == 0:
            log.warning(f"Input file is empty: {file_input.filename}")
            misc_errors.append(
                system_error("Input file is empty", error_type="warning")
            )
            _processing_metrics.record_error("empty-file")
            # Continue processing - empty file is handled by CSV reader

        # Dispatch to appropriate processor based on file type
        if file_input.validate_file_extension(["csv"]):
            # CSV file requires form configuration
            if not form_project_configs or not module:
                error_msg = (
                    "CSV file requires form_configs_file and module configuration"
                )
                log.error(error_msg)
                misc_errors.append(system_error(error_msg))
                _processing_metrics.record_error("missing-configuration")
                return False

            try:
                success = _process_csv_file(
                    file_input=file_input,
                    event_logger=event_logger,
                    gear_name=gear_name,
                    proxy=proxy,
                    context=context,
                    error_writer=error_writer,
                    form_project_configs=form_project_configs,
                    module=module,
                    misc_errors=misc_errors,
                )
            except Exception as e:
                error_msg = f"Unexpected error during CSV file processing: {e!s}"
                log.error(error_msg)
                misc_errors.append(system_error(error_msg))
                _processing_metrics.record_error("csv-processing-exception")
                # Don't return False here - continue to log metrics and complete
                # gracefully
                success = False

        # TODO: Add support for other single file types here
        # elif file_input.validate_file_extension(["json"]):
        #     success = _process_json_file(...)
        # elif file_input.validate_file_extension(["xlsx"]):
        #     success = _process_excel_file(...)
        else:
            error_msg = f"Unsupported file type: {file_input.filename}"
            log.warning(error_msg)
            misc_errors.append(system_error(error_msg, error_type="warning"))
            _processing_metrics.record_error("unsupported-file-type")
            return False

    except Exception as e:
        # Catch-all for any critical errors
        error_msg = f"Critical error in submission logger: {e!s}"
        log.error(error_msg)
        misc_errors.append(system_error(error_msg))
        _processing_metrics.record_error("critical-system-error")
        success = False

    finally:
        # Mark end of processing and log summary for operational monitoring
        _processing_metrics.end_processing()
        _processing_metrics.log_summary()

        # Add any miscellaneous system errors to the error writer for QC reporting
        # These are errors that couldn't be associated with specific visits
        if misc_errors:
            for error in misc_errors:
                error_writer.write(error)

        if success:
            log.info("File processing completed successfully")
        else:
            log.warning(
                "File processing completed with errors - check error logs for details"
            )

    return success
