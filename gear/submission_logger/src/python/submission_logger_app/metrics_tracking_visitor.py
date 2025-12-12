"""Metrics tracking visitor for submission logger."""

import logging
from typing import Any, Dict, List

from inputs.csv_reader import CSVVisitor

log = logging.getLogger(__name__)


class MetricsTrackingVisitor(CSVVisitor):
    """A CSV visitor that wraps another visitor and tracks processing
    metrics."""

    def __init__(self, wrapped_visitor: CSVVisitor, metrics_tracker):
        """Initialize the metrics tracking visitor.

        Args:
            wrapped_visitor: The visitor to wrap and track metrics for
            metrics_tracker: The ProcessingMetrics instance to update
        """
        self.__wrapped_visitor = wrapped_visitor
        self.__metrics = metrics_tracker
        self.__visits_processed = 0
        self.__visits_successful = 0
        self.__visits_failed = 0

    def visit_header(self, header: List[str]) -> bool:
        """Visit the header and track metrics.

        Args:
            header: The CSV header row

        Returns:
            True if header processing succeeded, False otherwise
        """
        try:
            result = self.__wrapped_visitor.visit_header(header)
            if not result:
                self.__metrics.record_error("header-validation-error")
            return result
        except Exception as e:
            log.error(f"Error processing header: {e!s}")
            self.__metrics.record_error("header-processing-exception")
            return False

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit a row and track metrics.

        Args:
            row: The CSV row data
            line_num: The line number

        Returns:
            True if row processing succeeded, False otherwise
        """
        self.__visits_processed += 1
        self.__metrics.increment_visits_found()

        try:
            result = self.__wrapped_visitor.visit_row(row, line_num)
            if result:
                self.__visits_successful += 1
                self.__metrics.increment_visits_processed_successfully()
                # Assume successful visit processing means event and QC log were created
                self.__metrics.increment_events_created()
                self.__metrics.increment_qc_logs_created()
            else:
                self.__visits_failed += 1
                self.__metrics.increment_visits_failed()
                self.__metrics.increment_events_failed()
                self.__metrics.increment_qc_logs_failed()
                self.__metrics.record_error("visit-processing-failed")
            return result
        except Exception as e:
            log.error(f"Error processing row {line_num}: {e!s}")
            self.__visits_failed += 1
            self.__metrics.increment_visits_failed()
            self.__metrics.increment_events_failed()
            self.__metrics.increment_qc_logs_failed()
            self.__metrics.record_error("visit-processing-exception")
            return False

    def get_processing_stats(self) -> Dict[str, int]:
        """Get processing statistics from this visitor.

        Returns:
            Dictionary with processing statistics
        """
        return {
            "visits_processed": self.__visits_processed,
            "visits_successful": self.__visits_successful,
            "visits_failed": self.__visits_failed,
        }
