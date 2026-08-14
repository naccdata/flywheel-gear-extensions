"""Date format validation for CSV row processing."""

import logging
from typing import Any, Dict

from nacc_common.data_identification import (
    DataIdentification,
)
from nacc_common.form_dates import DEFAULT_DATE_FORMAT, convert_date
from outputs.error_writer import ErrorWriter
from outputs.errors import unexpected_value_error

from inputs.csv_reader import RowValidator

log = logging.getLogger(__name__)


class DateValidator(RowValidator):
    """Row validator to check whether the row has a valid date entered in the
    date field."""

    def __init__(self, date_field: str, error_writer: ErrorWriter) -> None:
        self.__date_field = date_field
        self.__error_writer = error_writer

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that the row has a valid date entered in the date field.

        Args:
          row: the dictionary for the row
          line_number: the line number of the row

        Returns:
          True if the entered date is valid, False otherwise.
        """

        valid = False

        date = row.get(self.__date_field, "")
        if date:
            normalized_date = convert_date(
                date_string=date.strip(), date_format=DEFAULT_DATE_FORMAT
            )

            if normalized_date:
                valid = True

        if not valid:
            visit_keys = DataIdentification.from_form_record_safe(
                record=row, date_field=self.__date_field
            )
            self.__error_writer.write(
                unexpected_value_error(
                    field=self.__date_field,
                    value=date,
                    expected="",
                    message="Invalid Date",
                    line=line_number,
                    visit_keys=visit_keys,
                )
            )

        return valid
