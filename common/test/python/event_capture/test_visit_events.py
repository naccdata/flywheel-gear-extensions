from datetime import datetime

import pytest
from event_capture.visit_events import VisitEvent


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

    def test_module_normalization_to_uppercase(self):
        """Test that module is normalized to uppercase."""
        event = VisitEvent(
            action="submit",
            pipeline_adcid=0,
            project_label="ingest-form",
            center_label="sample-center",
            ptid="nacc123456",
            visit_date="2025-10-07",
            visit_number="v1",
            datatype="form",
            module="uds",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module == "UDS"

    def test_module_normalization_mixed_case(self):
        """Test that module with mixed case is normalized to uppercase."""
        event = VisitEvent(
            action="submit",
            pipeline_adcid=0,
            project_label="ingest-form",
            center_label="sample-center",
            ptid="nacc123456",
            visit_date="2025-10-07",
            visit_number="v1",
            datatype="form",
            module="Uds",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module == "UDS"

    def test_module_normalization_already_uppercase(self):
        """Test that uppercase module remains unchanged."""
        event = VisitEvent(
            action="submit",
            pipeline_adcid=0,
            project_label="ingest-form",
            center_label="sample-center",
            ptid="nacc123456",
            visit_date="2025-10-07",
            visit_number="v1",
            datatype="form",
            module="UDS",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module == "UDS"

    def test_module_normalization_none_preserved(self):
        """Test that None module is preserved (for non-form datatypes)."""
        event = VisitEvent(
            action="submit",
            pipeline_adcid=0,
            project_label="ingest-dicom",
            center_label="sample-center",
            ptid="ptid123",
            visit_date="2025-10-07",
            visit_number="v1",
            datatype="dicom",
            module=None,
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module is None

    def test_normalization_consistency_with_event_match_key(self):
        """Test that normalized module values are consistent with EventMatchKey
        expectations."""
        # Create event with lowercase module
        event = VisitEvent(
            action="submit",
            pipeline_adcid=0,
            project_label="ingest-form",
            center_label="sample-center",
            ptid="NACC123456",
            visit_date="2025-10-07",
            visit_number="v1",
            datatype="form",
            module="uds",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        # Module should be normalized to uppercase
        assert event.module == "UDS"

        # These normalized values should match EventMatchKey expectations
        from event_capture.models import EventMatchKey

        key = EventMatchKey(
            ptid=event.ptid, date=event.visit_date, module=event.module or ""
        )

        assert key.ptid == "NACC123456"
        assert key.module == "UDS"
