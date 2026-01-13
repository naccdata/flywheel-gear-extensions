from datetime import datetime
from typing import Any, Dict, List

from configs.ingest_configs import ModuleConfigs
from inputs.csv_reader import CSVVisitor
from keys.types import DatatypeNameType
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter
from outputs.errors import missing_field_error

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
        self.__event_capture = event_logger
        self.__module_configs = module_configs
        self.__error_writer = error_writer
        self.__action: VisitEventType = action
        self.__datatype: DatatypeNameType = datatype
        self.__timestamp = timestamp

    def visit_header(self, header: List[str]) -> bool:
        required_fields = set(self.__module_configs.required_fields)
        if not required_fields.issubset(set(header)):
            missing_fields = required_fields.difference(header)
            self.__error_writer.write(missing_field_error(set(missing_fields)))
            return False

        return True

    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        self.__error_writer.clear()

        module = row.get(FieldNames.MODULE, "").upper()
        if not module:
            return False

        packet = row.get(FieldNames.PACKET, "").upper()
        if not packet:
            return False

        visit_number = row.get(FieldNames.VISITNUM)
        if not visit_number:
            return False

        date_field = self.__module_configs.date_field
        visit_date = row.get(date_field)
        if not visit_date:
            return False

        ptid = row.get(FieldNames.PTID)
        if not ptid:
            return False

        adcid = row.get(FieldNames.ADCID)
        if not adcid:
            return False

        self.__event_capture.capture_event(
            VisitEvent(
                action=self.__action,
                pipeline_adcid=adcid,
                project_label=self.__project_label,
                center_label=self.__center_label,
                gear_name=self.__gear_name,
                ptid=ptid,
                visit_date=visit_date,
                visit_number=visit_number,
                datatype=self.__datatype,
                module=module,
                packet=packet,
                timestamp=self.__timestamp,
            )
        )
        return True
