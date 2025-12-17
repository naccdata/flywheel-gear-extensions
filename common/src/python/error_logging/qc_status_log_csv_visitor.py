"""CSV visitor for QC status log creation in submission logger."""

import logging
from typing import Any, Optional

from configs.ingest_configs import ModuleConfigs
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from inputs.csv_reader import CSVVisitor
from nacc_common.error_models import QCStatus, VisitKeys
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter

from error_logging.qc_status_log_creator import QCStatusLogManager

log = logging.getLogger(__name__)


class QCStatusLogCSVVisitor(CSVVisitor):
    """CSV visitor that creates QC status logs for each visit."""

    def __init__(
        self,
        module_configs: ModuleConfigs,
        project: ProjectAdaptor,
        qc_log_creator: QCStatusLogManager,
        gear_name: str,
        error_writer: ListErrorWriter,
        module_name: Optional[str] = None,
    ) -> None:
        """Initialize QC CSV visitor.

        Args:
            module_configs: Module configurations for field validation
            project: Project adaptor for QC log creation
            qc_log_creator: QC status log creator
            gear_name: Name of the gear
            error_writer: Error writer for tracking issues
            module_name: Optional module name to use when MODULE field is not
                present in the row. If None, uses row.get(FieldNames.MODULE).
        """
        self.__module_configs = module_configs
        self.__project = project
        self.__qc_log_creator = qc_log_creator
        self.__gear_name = gear_name
        self.__error_writer = error_writer
        self.__module_name = module_name
        self.__processed_visits: list[VisitKeys] = []

    def visit_header(self, header: list[str]) -> bool:
        """Validate CSV header - no specific requirements for QC visitor.

        Args:
            header: List of header names

        Returns:
            Always True - QC visitor doesn't add header requirements
        """
        return True

    def visit_row(self, row: dict[str, Any], line_num: int) -> bool:
        """Process a CSV row to create QC status logs.

        Args:
            row: CSV row data
            line_num: Line number in the CSV file

        Returns:
            True if processing was successful, False otherwise
        """
        # Extract visit information for QC log creation
        visit_keys = self._extract_visit_keys(row)
        if not visit_keys or not self._is_valid_visit(visit_keys):
            log.debug(f"Skipping row {line_num} - insufficient visit data")
            return True  # Don't fail processing for incomplete visits

        # Store visit keys for later file metadata enhancement
        self.__processed_visits.append(visit_keys)

        # Determine status based on error writer state
        has_errors = len(self.__error_writer.errors().root) > 0
        qc_status: QCStatus = "FAIL" if has_errors else "PASS"

        log.debug(
            f"QC status determination for visit ptid={visit_keys.ptid}, "
            f"date={visit_keys.date}: {qc_status} "
            f"(errors: {len(self.__error_writer.errors().root)})"
        )

        # Create QC status log with determined status
        qc_success = self.__qc_log_creator.update_qc_log(
            visit_keys=visit_keys,
            project=self.__project,
            gear_name=self.__gear_name,
            status=qc_status,
            errors=self.__error_writer.errors(),
            reset_qc_metadata="ALL",
            add_visit_metadata=True,
        )

        if not qc_success:
            log.warning(
                f"Failed to create QC status log for visit: "
                f"ptid={visit_keys.ptid}, date={visit_keys.date}, "
                f"module={visit_keys.module}"
            )
            # Don't fail the entire processing for QC log creation failure
            # This allows event logging to continue even if QC log creation fails

        return True

    def _extract_visit_keys(self, row: dict[str, Any]) -> VisitKeys:
        """Extract visit keys from a CSV row.

        Args:
            row: CSV row data

        Returns:
            VisitKeys object with visit identification information
        """
        date_field = self.__module_configs.date_field

        # Determine module name: use provided module_name or get from row
        if self.__module_name:
            module = self.__module_name.upper()
        else:
            module = row.get(FieldNames.MODULE, "").upper()

        return VisitKeys(
            ptid=row.get(FieldNames.PTID),
            date=row.get(date_field),
            visitnum=row.get(FieldNames.VISITNUM),
            module=module,
            adcid=int(row[FieldNames.ADCID]) if row.get(FieldNames.ADCID) else None,
        )

    def _is_valid_visit(self, visit_keys: VisitKeys) -> bool:
        """Check if visit keys contain sufficient information for QC log
        creation.

        Args:
            visit_keys: Visit identification information

        Returns:
            True if visit has required fields, False otherwise
        """
        return bool(visit_keys.ptid and visit_keys.date and visit_keys.module)

    def get_processed_visits(self) -> list[VisitKeys]:
        """Get the list of visits processed from the CSV file.

        Returns:
            List of VisitKeys for all successfully processed visits
        """
        return self.__processed_visits.copy()
