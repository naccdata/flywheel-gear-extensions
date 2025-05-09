"""Defines NCRAD Biomarker Mapping."""
import logging
import re
from typing import Any, Dict, List, Optional, TextIO

from flywheel import FileSpec
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from gear_execution.gear_execution import GearExecutionError
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import (
    ListErrorWriter,
    empty_field_error,
    missing_field_error,
    unexpected_value_error,
)
from outputs.outputs import write_csv_to_stream
from projects.project_mapper import build_project_map

log = logging.getLogger(__name__)


class NCRADCSVVisitor(CSVVisitor):
    """Visitor for NCRAD CSVs."""

    # used to determine if something is plate/well data
    PLATE_LAYOUT_KEY = 'plate_layout_position'
    PLATE_PATTERN = re.compile(r"plate\s+(\d+)\s+-\s+well\s+[a-z0-9]+")

    def __init__(self, error_writer: ListErrorWriter) -> None:
        """Initializer."""
        self.error_writer: ListErrorWriter = error_writer
        self.headers: List[str] = []
        self.data: List[Dict[str, Any]] = []

    def create_file_spec(self, name: str, adcid: str) -> FileSpec:
        """Creates file spec from the data.

        Args:
            name: Filename
            adcid: ADCID to prefix if filename does not already start
                with it
        Returns:
            FileSpec
        """
        contents = write_csv_to_stream(headers=self.headers,
                                       data=self.data).getvalue()
        if not name.startswith(adcid):
            name = f"{adcid}_{name}"

        return FileSpec(name=name,
                        contents=contents,
                        content_type="text/csv",
                        size=len(contents))

    def get_plate_num(self, row: Dict[str, Any],
                      line_num: int) -> Optional[int]:
        """Grabs the plate number from the row.

        Args:
            row: The dictionary for a row from a CSV file
            line_num: The line number of the row
        Returns:
            The plate number if found, None otherwise
        """
        # make lowercase for consistency, we only need the plate number
        plate_num = None
        plate = row.get(self.PLATE_LAYOUT_KEY, "").strip()
        match = re.search(self.PLATE_PATTERN, plate.lower())
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

        if plate_num is None:
            # did not get plate number, report error
            error = unexpected_value_error(
                field=self.PLATE_LAYOUT_KEY,
                value=plate,
                expected=str(self.PLATE_PATTERN),
                line=line_num,
                message=f"Invalid or missing plate layout: {plate}")
            self.error_writer.write(error)

        return plate_num


class NCRADBiomarkerCSVVisitor(NCRADCSVVisitor):
    """Visitor for the NCRAD Biomarker CSV."""

    def __init__(self, error_writer: ListErrorWriter):
        """Initiailzer."""
        super().__init__(error_writer)
        self.__adcid: str | None = None
        self.__is_plate_data: bool = False
        self.__plates: List[int] = []

        # expected headers (assumes CSV center splitter was
        # run before this and normalized the header names)
        # these fields cannot be null
        self.__expected_headers: List[str] = [
            'adcid',  # transformed
            'ptid',  # transformed
            'barcode',
            'kit_number',
            'collection_date',
            'patient_id'
        ]

    @property
    def plates(self) -> List[int]:
        return self.__plates

    @property
    def adcid(self) -> str | None:
        return self.__adcid

    def visit_header(self, header: List[str]) -> bool:
        """Normalizes header and verifies it is as expected. Also determines if
        this is plate/well data by existence of the plate layout key.

        Args:
            header: Header list to verify
        Returns:
            True if the header is valid, False otherwise
        """
        for i, field in enumerate(header):
            # transform these fields
            if field == 'adrc_site':
                header[i] = 'adcid'
            if field == 'pt_id':
                header[i] = 'ptid'

        missing = set(self.__expected_headers) - set(header)
        if missing:
            for field in missing:
                error = missing_field_error(field)
                self.error_writer.write(error)
            return False

        self.headers = header
        self.__is_plate_data = self.PLATE_LAYOUT_KEY in self.headers
        if self.__is_plate_data:
            self.__expected_headers.append(self.PLATE_LAYOUT_KEY)

        return True

    def check_required_fields(self, row: Dict[str, Any],
                              line_num: int) -> bool:
        """Checks required fields.

        Args:
          row: The dictionary for a row from a CSV file
          line_num: The line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        success = True

        # check required headers
        for field in self.__expected_headers:
            if not row[field]:
                success = False
                error = empty_field_error(
                    field=field,
                    line=line_num,
                    message=f"Row {line_num} was invalid: Missing {field}")
                self.error_writer.write(error)

        # check ADCID - use first one found as expected value
        row_adcid = row['adcid'].strip()
        if not self.__adcid:
            self.__adcid = row_adcid
        elif row_adcid != self.__adcid:
            error = unexpected_value_error(
                field='adcid',
                value=row_adcid,
                expected=self.__adcid,
                line=line_num,
                message=f"Row {line_num} had unexpected ADCID: {row_adcid}")
            self.error_writer.write(error)
            success = False

        return success

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit the dictionary for a row. Checks all fields in
        EXPECTED_HEADERS are non-empty, and that all ADCIDs match. If plate
        layout, keep track of plates.

        Args:
          row: The dictionary for a row from a CSV file
          line_num: The line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        if not self.check_required_fields(row, line_num):
            return False

        # check for plates
        if self.__is_plate_data:
            plate_num = self.get_plate_num(row, line_num)
            if plate_num is None:
                return False

            self.__plates.append(plate_num)

        self.data.append(row)
        return True


class NCRADBiomarkerQCCSVVisitor(NCRADCSVVisitor):
    """Visitor for biomarker QC CSV."""

    def __init__(self, plates: List[int],
                 error_writer: ListErrorWriter) -> None:
        """Initializer."""
        super().__init__(error_writer)
        self.__plates: List[int] = plates

    def visit_header(self, header: List[str]) -> bool:
        """Visits QC header - only cares about plate key if
        there are plates.

        Args:
            header: Header list to verify
        Returns:
            True if the header is valid, False otherwise
        """
        result = (not self.__plates) or (self.PLATE_LAYOUT_KEY in header)
        if not result:
            error = missing_field_error(self.PLATE_LAYOUT_KEY)
            self.error_writer.write(error)

        self.headers = header
        return result

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        """Visit the dictionary for a row. Only keeps if plate number is in
        plates, or all if no plates specified.

        Args:
          row: The dictionary for a row from a CSV file
          line_num: The line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        if not self.__plates:
            self.data.append(row)
            return True

        plate_num = self.get_plate_num(row, line_num)
        if plate_num is None:
            return False
        elif plate_num in self.__plates:
            self.data.append(row)

        return True


def run(proxy: FlywheelProxy, biomarker_file: TextIO, qc_file: TextIO,
        biomarker_filename: str, qc_filename: str,
        error_writer: ListErrorWriter, target_project: str) -> bool:
    """Runs the NCRAD Biomarker Mapping process. Visits both the biomarker and
    QC NCRAD files.

    Args:
        proxy: the proxy for the Flywheel instance
        biomarker_file: Input biomarker data
        qc_file: Corresponding QC file
        biomarker_filename: Name to give output biomarker file
        qc_filename: Name to give output QC file
        error_writer: ListErrorWriter to write errors to
        target_project: Target project to write results to
    Returns:
        Whether or not the files were read successfully
    """
    bio_visitor = NCRADBiomarkerCSVVisitor(error_writer=error_writer)
    success = read_csv(input_file=biomarker_file,
                       error_writer=error_writer,
                       visitor=bio_visitor,
                       preserve_case=False)

    if not success:
        log.error("Failed to read biomarker CSV")
        return False

    qc_visitor = NCRADBiomarkerQCCSVVisitor(error_writer=error_writer,
                                            plates=bio_visitor.plates)
    success = read_csv(input_file=qc_file,
                       error_writer=error_writer,
                       visitor=qc_visitor,
                       preserve_case=False)

    if not success:
        log.error("Failed to read or split biomarker QC CSV")
        return False

    # find target project to upload results to
    adcid = bio_visitor.adcid
    if adcid is None:
        raise GearExecutionError(
            "Could not determine ADCID from biomarker file")

    project_map = build_project_map(proxy=proxy,
                                    destination_label=target_project,
                                    center_filter=[adcid])
    project = project_map.get(f'adcid-{adcid}')
    if not project:
        raise GearExecutionError(
            f'Failed to find {target_project} for ADCID {adcid}')

    bio_spec = bio_visitor.create_file_spec(biomarker_filename, adcid)
    qc_spec = qc_visitor.create_file_spec(qc_filename, adcid)

    if proxy.dry_run:
        log.info(
            f"DRY RUN: Would have written the following files to {project.id}")
        for file in [bio_spec, qc_spec]:
            log.info(f"DRY RUN: {file.name}")
    else:
        for file in [bio_spec, qc_spec]:
            project.upload_file(file)  # type: ignore
            log.info(f"Wrote {file.name} to {project.id}")

    return True
