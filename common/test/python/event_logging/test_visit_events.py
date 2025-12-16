from datetime import datetime

import pytest
from event_logging.visit_events import VisitEvent


class TestVisitEvent:
    def test_datatype(self):
        try:
            valid_event = VisitEvent(
                action="submit",
                pipeline_adcid=0,
                project_label="ingest-form",
                center_label="sample-center",
                ptid="dummy",
                visit_date="2025-10-07",
                visit_number="v1",
                datatype="form",
                module="UDS",
                timestamp=datetime.now(),
                gear_name="dummy-gear",
            )
            assert valid_event is not None
        except ValueError as error:
            raise AssertionError(error) from error

        with pytest.raises(ValueError):
            VisitEvent(
                action="submit",
                pipeline_adcid=0,
                project_label="ingest-dicom",
                center_label="sample-center",
                ptid="dummy",
                visit_date="2025-10-07",
                visit_number="v1",
                datatype="dicom",
                module="UDS",
                timestamp=datetime.now(),
                gear_name="dummy-gear",
            )
