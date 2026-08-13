"""Unit tests for ACTION_DUPLICATE_SUBMIT constant and VisitEvent acceptance.

Validates: Requirements 1.1, 1.2, 1.3
"""

from datetime import datetime

import pytest
from event_capture.visit_events import ACTION_DUPLICATE_SUBMIT, VisitEvent
from nacc_common.data_identification import DataIdentification


class TestActionDuplicateSubmitConstant:
    """Tests for the ACTION_DUPLICATE_SUBMIT constant (Requirement 1.2)."""

    def test_action_duplicate_submit_value(self):
        """ACTION_DUPLICATE_SUBMIT equals 'duplicate-submit'."""
        assert ACTION_DUPLICATE_SUBMIT == "duplicate-submit"


class TestVisitEventDuplicateSubmitAcceptance:
    """Tests for VisitEvent acceptance of action='duplicate-submit'
    (Requirements 1.1, 1.3)."""

    def test_accepts_duplicate_submit_with_form_data(self):
        """VisitEvent accepts action='duplicate-submit' with datatype='form'
        and FormIdentification."""
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="dummy",
            date="2025-10-07",
            visitnum="v1",
            module="UDS",
        )
        event = VisitEvent(
            action="duplicate-submit",
            project_label="ingest-form",
            center_label="sample-center",
            data_identification=data_id,
            datatype="form",
            timestamp=datetime.now(),
            gear_name="form-transformer",
        )
        assert event is not None
        assert event.action == "duplicate-submit"

    def test_rejects_duplicate_submit_with_non_form_data(self):
        """VisitEvent rejects action='duplicate-submit' with datatype='form'
        and non-FormIdentification data (ImageIdentification)."""
        data_id = DataIdentification.from_visit_metadata(
            adcid=0,
            ptid="dummy",
            date="2025-10-07",
            visitnum="v1",
            modality="MR",
        )
        with pytest.raises(ValueError):
            VisitEvent(
                action="duplicate-submit",
                project_label="ingest-form",
                center_label="sample-center",
                data_identification=data_id,
                datatype="form",
                timestamp=datetime.now(),
                gear_name="form-transformer",
            )
