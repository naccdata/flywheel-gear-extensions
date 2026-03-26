from datetime import datetime

import pytest
from event_capture.visit_events import VisitEvent
from nacc_common.data_identification import DataIdentification


class TestVisitEvent:
    def test_datatype(self):
        try:
            data_id = DataIdentification.from_visit_metadata(
                adcid=0,
                ptid="dummy",
                date="2025-10-07",
                visitnum="v1",
                module="UDS",
            )
            valid_event = VisitEvent(
                action="submit",
                project_label="ingest-form",
                center_label="sample-center",
                data_identification=data_id,
                datatype="form",
                timestamp=datetime.now(),
                gear_name="dummy-gear",
            )
            assert valid_event is not None
        except ValueError as error:
            raise AssertionError(error) from error

        with pytest.raises(ValueError):
            data_id = DataIdentification.from_visit_metadata(
                adcid=0,
                ptid="dummy",
                date="2025-10-07",
                visitnum="v1",
                module="UDS",
            )
            VisitEvent(
                action="submit",
                project_label="ingest-dicom",
                center_label="sample-center",
                data_identification=data_id,
                datatype="dicom",
                timestamp=datetime.now(),
                gear_name="dummy-gear",
            )

    def test_module_normalization_to_uppercase(self):
        """Test that module is normalized to uppercase."""
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="nacc123456",
            date="2025-10-07",
            visitnum="v1",
            module="uds",
        )
        event = VisitEvent(
            action="submit",
            project_label="ingest-form",
            center_label="sample-center",
            data_identification=data_id,
            datatype="form",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module == "UDS"

    def test_module_normalization_mixed_case(self):
        """Test that module with mixed case is normalized to uppercase."""
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="nacc123456",
            date="2025-10-07",
            visitnum="v1",
            module="Uds",
        )
        event = VisitEvent(
            action="submit",
            project_label="ingest-form",
            center_label="sample-center",
            data_identification=data_id,
            datatype="form",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module == "UDS"

    def test_module_normalization_already_uppercase(self):
        """Test that uppercase module remains unchanged."""
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="nacc123456",
            date="2025-10-07",
            visitnum="v1",
            module="UDS",
        )
        event = VisitEvent(
            action="submit",
            project_label="ingest-form",
            center_label="sample-center",
            data_identification=data_id,
            datatype="form",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        assert event.module == "UDS"

    def test_module_normalization_none_preserved(self):
        """Test that module attribute doesn't exist for image datatypes."""
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="ptid123",
            date="2025-10-07",
            visitnum="v1",
            modality="MR",  # Use modality for image data
        )
        event = VisitEvent(
            action="submit",
            project_label="ingest-dicom",
            center_label="sample-center",
            data_identification=data_id,
            datatype="dicom",
            timestamp=datetime.now(),
            gear_name="dummy-gear",
        )

        # Image events don't have module attribute
        with pytest.raises(AttributeError):
            _ = event.module

    def test_normalization_consistency_with_event_match_key(self):
        """Test that normalized module values are consistent with EventMatchKey
        expectations."""
        # Create event with lowercase module
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="NACC123456",
            date="2025-10-07",
            visitnum="v1",
            module="uds",
        )
        event = VisitEvent(
            action="submit",
            project_label="ingest-form",
            center_label="sample-center",
            data_identification=data_id,
            datatype="form",
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
