"""Assertion helpers for event logging testing."""

from datetime import datetime
from typing import Optional

from event_logging.visit_events import ACTION_PASS_QC, VisitEvent
from nacc_common.error_models import VisitMetadata


def assert_valid_qc_pass_event(
    event: VisitEvent,
    expected_ptid: str,
    expected_visit_date: str,
    expected_visit_number: str,
    expected_module: str,
    expected_packet: Optional[str] = None,
    expected_gear_name: str = "form-scheduler",
    expected_datatype: str = "form",
) -> None:
    """Assert that an event is a valid QC-pass event with expected values.

    Args:
        event: The VisitEvent to validate
        expected_ptid: Expected participant ID
        expected_visit_date: Expected visit date
        expected_visit_number: Expected visit number
        expected_module: Expected module
        expected_packet: Expected packet (optional)
        expected_gear_name: Expected gear name
        expected_datatype: Expected datatype
    """
    assert event.action == ACTION_PASS_QC, (
        f"Event action should be {ACTION_PASS_QC}, got {event.action}"
    )
    assert event.gear_name == expected_gear_name, (
        f"Event gear_name should be '{expected_gear_name}', got {event.gear_name}"
    )
    assert event.datatype == expected_datatype, (
        f"Event datatype should be '{expected_datatype}', got {event.datatype}"
    )
    assert event.ptid == expected_ptid, (
        f"Event PTID should be '{expected_ptid}', got {event.ptid}"
    )
    assert event.visit_date == expected_visit_date, (
        f"Event visit_date should be '{expected_visit_date}', got {event.visit_date}"
    )
    assert event.visit_number == expected_visit_number, (
        f"Event visit_number should be '{expected_visit_number}', "
        f"got {event.visit_number}"
    )
    assert event.module == expected_module, (
        f"Event module should be '{expected_module}', got {event.module}"
    )
    assert event.packet == expected_packet, (
        f"Event packet should be '{expected_packet}', got {event.packet}"
    )
    assert isinstance(event.timestamp, datetime), (
        "Event timestamp should be datetime object"
    )


def assert_event_structure_matches(
    event: VisitEvent,
    expected_project_label: str,
    expected_center_label: str,
    expected_pipeline_adcid: int,
    expected_study: Optional[str] = None,
) -> None:
    """Assert that an event has the expected structure and project information.

    Args:
        event: The VisitEvent to validate
        expected_project_label: Expected project label
        expected_center_label: Expected center label
        expected_pipeline_adcid: Expected pipeline ADCID
        expected_study: Expected study name (optional)
    """
    # Required fields for backward compatibility
    required_fields = [
        "action",
        "study",
        "pipeline_adcid",
        "project_label",
        "center_label",
        "gear_name",
        "ptid",
        "visit_date",
        "visit_number",
        "datatype",
        "module",
        "packet",
        "timestamp",
    ]

    for field in required_fields:
        assert hasattr(event, field), f"Event must have required field '{field}'"

    # Verify specific project information
    assert event.project_label == expected_project_label, (
        f"Event project_label should be '{expected_project_label}', "
        f"got {event.project_label}"
    )
    assert event.center_label == expected_center_label, (
        f"Event center_label should be '{expected_center_label}', "
        f"got {event.center_label}"
    )
    assert event.pipeline_adcid == expected_pipeline_adcid, (
        f"Event pipeline_adcid should be {expected_pipeline_adcid}, "
        f"got {event.pipeline_adcid}"
    )

    if expected_study:
        assert event.study == expected_study, (
            f"Event study should be '{expected_study}', got {event.study}"
        )

    # Verify data types
    assert isinstance(event.timestamp, datetime), "Timestamp must be datetime object"
    assert isinstance(event.pipeline_adcid, int), "Pipeline ADCID must be integer"


def assert_visit_metadata_matches(
    actual: VisitMetadata,
    expected_ptid: str,
    expected_date: str,
    expected_module: str,
    expected_visitnum: Optional[str] = None,
    expected_packet: Optional[str] = None,
) -> None:
    """Assert that visit metadata matches expected values.

    Args:
        actual: The VisitMetadata to validate
        expected_ptid: Expected participant ID
        expected_date: Expected visit date
        expected_module: Expected module
        expected_visitnum: Expected visit number (optional)
        expected_packet: Expected packet (optional)
    """
    assert actual.ptid == expected_ptid, (
        f"VisitMetadata PTID should be '{expected_ptid}', got {actual.ptid}"
    )
    assert actual.date == expected_date, (
        f"VisitMetadata date should be '{expected_date}', got {actual.date}"
    )
    assert actual.module == expected_module, (
        f"VisitMetadata module should be '{expected_module}', got {actual.module}"
    )

    if expected_visitnum is not None:
        assert actual.visitnum == expected_visitnum, (
            f"VisitMetadata visitnum should be '{expected_visitnum}', "
            f"got {actual.visitnum}"
        )

    if expected_packet is not None:
        assert actual.packet == expected_packet, (
            f"VisitMetadata packet should be '{expected_packet}', got {actual.packet}"
        )


def assert_event_serializable(event: VisitEvent) -> None:
    """Assert that an event can be serialized (important for S3 storage).

    Args:
        event: The VisitEvent to test for serializability
    """
    try:
        event_dict = event.model_dump()
        assert isinstance(event_dict, dict), "Event should serialize to dictionary"

        # Verify key fields are present in serialized form
        assert "action" in event_dict, "Serialized event should contain 'action'"
        assert "gear_name" in event_dict, "Serialized event should contain 'gear_name'"
        assert "ptid" in event_dict, "Serialized event should contain 'ptid'"
        assert "timestamp" in event_dict, "Serialized event should contain 'timestamp'"

        # Verify values are correct in serialized form
        assert event_dict["action"] == ACTION_PASS_QC, (
            "Serialized action should be 'pass-qc'"
        )

    except Exception as e:
        raise AssertionError(
            f"Event should be serializable for S3 storage, but got error: {e}"
        ) from e
