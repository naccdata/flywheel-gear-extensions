"""Center validation for CSV row processing."""

import logging
import re
from typing import Any, Dict, Optional

from identifiers.model import PTID_PATTERN
from keys.keys import SysErrorCodes
from nacc_common.error_models import VisitKeys
from nacc_common.field_names import FieldNames
from outputs.error_writer import ErrorWriter
from outputs.errors import preprocessing_error

from inputs.csv_reader import RowValidator

log = logging.getLogger(__name__)


class CenterValidator(RowValidator):
    """Row validator to check whether the row has the correct ADCID and the
    PTID matches expected format."""

    def __init__(
        self, center_id: int, date_field: Optional[str], error_writer: ErrorWriter
    ) -> None:
        self.__center_id = center_id
        self.__date_field = date_field
        self.__error_writer = error_writer

    def check(self, row: Dict[str, Any], line_number: int) -> bool:
        """Checks that the row has the expected ADCID and the PTID matches
        expected format.

        Args:
          row: the dictionary for the row
          line_number: the line number of the row

        Returns:
          True if the ADCID matches and PTID in expected format, False otherwise.
        """

        valid = True
        if str(row.get(FieldNames.ADCID)) != str(self.__center_id):
            log.error("Center ID for project must match form ADCID")
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.ADCID,
                    value=row[FieldNames.ADCID],
                    line=line_number,
                    error_code=SysErrorCodes.ADCID_MISMATCH,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=self.__date_field
                    ),
                )
            )
            valid = False

        ptid = row.get(FieldNames.PTID, "")
        if not re.fullmatch(PTID_PATTERN, ptid):
            self.__error_writer.write(
                preprocessing_error(
                    field=FieldNames.PTID,
                    value=ptid,
                    line=line_number,
                    error_code=SysErrorCodes.INVALID_PTID,
                    visit_keys=VisitKeys.create_from(
                        record=row, date_field=self.__date_field
                    ),
                )
            )
            valid = False

        return valid
