"""Defines NCRAD Biomarker Mapping."""
import logging
import re
from io import StringIO
from typing import Any, Dict, List, TextIO

from flywheel import FileSpec
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from inputs.csv_reader import CSVVisitor, read_csv
from outputs.errors import (
    ListErrorWriter,
    empty_field_error,
    missing_field_error,
    unexpected_value_error,
)
from outputs.outputs import write_csv_to_stream

log = logging.getLogger(__name__)


class NCRADCSVVisitor(CSVVisitor):
    """Visitor for NCRAD CSVs."""

    # used to determine if something is plate/well data
    PLATE_LAYOUT_KEY = 'plate_layout_position'
    PLATE_PATTERN = re.compile(r"plate\s+(\d+)\s+-\s+well\s+[a-z0-9]+")

    def __init__(self, error_writer: ListErrorWriter) -> None:
        """Initializer."""
        self.__error_writer: ListErrorWriter = error_writer
        self.__headers: List[str] = []
        self.__data: List[Dict[str, Any]] = []

    @property
    def headers(self) -> List[str]:
        return self.__headers

    @property
    def data(self) -> List[Dict[str, Any]]:
        return self.__data

    @property
    def error_writer(self) -> ListErrorWriter:
        return self.__error_writer

    def get_read_contents(self) -> StringIO:
        """Returns the read and validated contents."""
        return write_csv_to_stream(headers=self.__headers,
                                   data=self.__data)

    def get_plate_num(self, row: Dict[str, Any], line_num: int) -> Optional[int]:
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
                field=PLATE_LAYOUT_KEY,
                value=plate,
                expected=PLATE_PATTERN,
                line=line_num,
                message=f"Invalid or missing plate layout: {plate}")
            self.__error_writer.write(error)

        return plate_num


class NCRADBiomarkerCSVVisitor(NCRADCSVVisitor):
    """Visitor for the NCRAD Biomarker CSV"""

    # expected headers (assumes CSV center splitter was
    # run before this and normalized the header names)
    # these fields cannot be null
    EXPECTED_FIELDS = [
        'adcid',  # transformed
        'ptid',   # transformed
        'barcode',
        'kit_number',
        'collection_date',
        'patient_id'
    ]

    def __init__(self, error_writer: ListErrorWriter):
        """Initiailzer."""
        super().__init__(error_writer)
        self.__adcid: int = None
        self.__is_plate_data: bool = False
        self.__plates: List[int] = []

    @property
    def plates(self) -> List[int]:
        return self.__plates

    def visit_header(self, header: List[str]) -> bool:
        """Normalizes header and verifies it is as expected.
        Also determines if this is plate/well data by existence
        of the plate layout key

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

        missing = set(self.EXPECTED_FIELDS) - set(header)
        if missing:
            for field in missing:
                error = missing_field_error(field)
                self.error_writer.write(error)
            return False

        self.headers = header
        self.__is_plate_data = self.PLATE_LAYOUT_KEY in self.headers

        return True

    def check_required_fields(self, row: Dict[str, Any], line_num: int) -> bool:
        """Checks required fields.
        Args:
          row: The dictionary for a row from a CSV file
          line_num: The line number of the row
        Returns:
          True if the row was processed without error, False otherwise
        """
        success = True
        expected_fields = self.EXPECTED_FIELDS
        if self.__is_plate_data:
            expected_fields = expected_fields + [self.PLATE_LAYOUT_KEY]

        # check required headers
        for field in expected_fields:
            if not row[field]:
                success = False
                error = empty_field_error(
                    field=field,
                    line=line_num,
                    message=f"Row {line_num} was invalid: Missing {field}")
                self.error_writer.write(error)

        # check ADCID - use first one found as expected value
        row_adcid = row['adcid']
        if not self.__adcid:
            self.__adcid = row_adcid
        elif not row_adcid == self.__adcid:
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
        EXPECTED_HEADERS are non-empty, and that all ADCIDs match. If
        plate layout, keep track of plates.

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

    def __init__(self,
                 plates: List[int],
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
        """Visit the dictionary for a row. Only keeps if plate
        number is in plates, or all if no plates specified.

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


def run(proxy: FlywheelProxy,
        biomarker_file: TextIO,
        qc_file: TextIO,
        error_writer: ListErrorWriter) -> Tuple[StringIO, StringIO]:
    """Runs the NCRAD Biomarker Mapping process. Visits
    both the biomarker and QC NCRAD files.

    Args:
        proxy: the proxy for the Flywheel instance
        biomarker_file: Input biomarker data
        qc_file: Corresponding QC file
        error_writer: ListErrorWriter to write errors to
    Returns:
        Tuple containing the contents for Biomarker and QC files
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


    biomarker_contents = visitor.get_read_contents()
    return biomarker_contents, qc_contents
