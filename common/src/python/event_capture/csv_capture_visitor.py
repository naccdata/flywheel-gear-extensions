from datetime import datetime
from typing import Any, Dict, List

from configs.ingest_configs import ConfigsError, ModuleConfigs
from inputs.csv_reader import CSVVisitor
from keys.types import DatatypeNameType
from nacc_common.data_identification import (
    DataIdentification,
    EmptyFieldError,
    InvalidDateError,
)
from outputs.error_writer import ListErrorWriter
from outputs.errors import empty_field_error, unexpected_value_error

from event_capture.event_capture import VisitEventCapture
from event_capture.visit_events import VisitEvent, VisitEventType


class CSVCaptureVisitor(CSVVisitor):
    def __init__(
        self,
        center_label: str,
        project_label: str,
        gear_name: str,
        event_capture: VisitEventCapture,
        module_configs: ModuleConfigs,
        error_writer: ListErrorWriter,
        timestamp: datetime,
        action: VisitEventType = "submit",
        datatype: DatatypeNameType = "form",
    ) -> None:
        self.__center_label = center_label
        self.__project_label = project_label
        self.__gear_name = gear_name
        self.__event_capture = event_capture
        self.__module_configs = module_configs
        self.__error_writer = error_writer
        self.__action: VisitEventType = action
        self.__datatype: DatatypeNameType = datatype
        self.__timestamp = timestamp

    def visit_header(self, header: List[str]) -> bool:
        # No validation needed - NACCIDLookupVisitor already validates required fields
        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        self.__error_writer.clear()

        # date field is module-specific
        date_field = self.__module_configs.date_field
        if date_field is None:
            raise ConfigsError(
                "Module configuration is missing required date_field setting"
            )

        try:
            data_id = DataIdentification.from_form_record(row, date_field)
        except EmptyFieldError as error:
            self.__error_writer.write(empty_field_error(error.fieldname, line=line_num))
            return True  # Don't fail - just skip event logging
        except InvalidDateError as error:
            self.__error_writer.write(
                unexpected_value_error(
                    field=error.date_field,
                    value=error.value,
                    expected="valid date",
                    message="Expected a valid date string",
                    line=line_num,
                )
            )
            return True  # Don't fail - just skip event logging

        self.__event_capture.capture_event(
            VisitEvent(
                action=self.__action,
                project_label=self.__project_label,
                center_label=self.__center_label,
                gear_name=self.__gear_name,
                data_identification=data_id,
                datatype=self.__datatype,
                timestamp=self.__timestamp,
            )
        )
        return True
