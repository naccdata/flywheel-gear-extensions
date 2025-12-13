"""Processing metrics for operational monitoring.

This module provides the ProcessingMetrics class for tracking processing
statistics across various gears and operations.
"""

import logging
from typing import Dict

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
        self.error_types: Dict[str, int] = {}
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
