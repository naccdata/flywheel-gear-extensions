"""Property test for DataIdentification model.

**Feature: form-scheduler-event-logging-refactor,
  Property 9: Extended Visit Metadata Model**
**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
"""

from typing import Any, Dict

from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import DataIdentification, VisitKeys


@st.composite
def visit_keys_strategy(draw):
    """Generate random VisitKeys data."""
    return {
        "adcid": draw(st.one_of(st.none(), st.integers(min_value=1, max_value=999))),
        "ptid": draw(st.one_of(st.none(), st.text(min_size=1, max_size=10))),
        "visitnum": draw(st.one_of(st.none(), st.text(min_size=1, max_size=3))),
        "module": draw(st.one_of(st.none(), st.text(min_size=1, max_size=10))),
        "date": draw(
            st.one_of(st.none(), st.dates().map(lambda d: d.strftime("%Y-%m-%d")))
        ),
        "naccid": draw(st.one_of(st.none(), st.text(min_size=1, max_size=15))),
    }


@st.composite
def visit_metadata_strategy(draw):
    """Generate random DataIdentification data."""
    visit_keys_data = draw(visit_keys_strategy())
    packet = draw(st.one_of(st.none(), st.text(min_size=1, max_size=5)))

    return {**visit_keys_data, "packet": packet}


@given(visit_data=visit_metadata_strategy())
@settings(max_examples=100)
def test_visit_metadata_to_visit_event_fields_mapping(visit_data: Dict[str, Any]):
    """Property test: DataIdentification serialization includes all fields.

      **Feature: form-scheduler-event-logging-refactor,
    Property 9: Extended Visit Metadata Model**
      **Validates: Requirements 7.3, 7.4, 7.5**

      For any DataIdentification instance, model serialization should include
      all required fields with their natural names.
    """
    # Arrange - Create DataIdentification instance
    visit_metadata = DataIdentification.from_visit_metadata(**visit_data)

    # Act - Get serialized fields
    event_fields = visit_metadata.model_dump()

    # Assert - Should return a dictionary
    assert isinstance(event_fields, dict), "model_dump should return a dictionary"

    # Assert - Should have all expected fields with natural names
    expected_fields = [
        "ptid",
        "date",
        "visitnum",
        "module",
        "packet",
        "adcid",
        "naccid",
    ]
    for field in expected_fields:
        assert field in event_fields, f"Event fields should contain {field}"

    # Assert - Field values should match
    assert event_fields["ptid"] == visit_metadata.ptid, "ptid should match"
    assert event_fields["date"] == visit_metadata.date, "date should match"
    assert event_fields["visitnum"] == visit_metadata.visitnum, "visitnum should match"
    assert event_fields["module"] == visit_metadata.module, "module should match"
    assert event_fields["packet"] == visit_metadata.packet, "packet should match"
    assert event_fields["adcid"] == visit_metadata.adcid, "adcid should match"
    assert event_fields["naccid"] == visit_metadata.naccid, "naccid should match"


def test_visit_metadata_with_packet_field():
    """Test DataIdentification with packet field for form packet information.

      **Feature: form-scheduler-event-logging-refactor,
    Property 9: Extended Visit Metadata Model**
      **Validates: Requirements 7.1, 7.2**

      DataIdentification should include an optional packet field for form packet
      information.
    """
    # Arrange & Act - Create DataIdentification with packet
    visit_metadata = DataIdentification.from_visit_metadata(
        ptid="TEST001", date="2024-01-15", visitnum="01", module="UDS", packet="I"
    )

    # Assert - Packet field should be available and correct
    assert visit_metadata.packet == "I", (
        "DataIdentification should store packet information"
    )

    # Act - Create DataIdentification without packet (should default to None)
    visit_metadata_no_packet = DataIdentification.from_visit_metadata(
        ptid="TEST002", date="2024-01-16", visitnum="02", module="UDS"
    )

    # Assert - Packet should default to None
    assert visit_metadata_no_packet.packet is None, (
        "DataIdentification packet should default to None"
    )


def test_visit_metadata_field_name_mapping():
    """Test DataIdentification field serialization with natural names.

    **Feature: form-scheduler-event-logging-refactor,
      Property 9: Extended Visit Metadata Model**
    **Validates: Requirements 7.3, 7.4, 7.5**

    DataIdentification serialization should use natural field names.
    """
    # Arrange - Create DataIdentification with all fields
    visit_metadata = DataIdentification.from_visit_metadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum="01",
        module="UDS",
        packet="I",
        adcid=123,
        naccid="NACC123456",
    )

    # Act - Get serialized fields
    event_fields = visit_metadata.model_dump()

    # Assert - Field names should be natural (not mapped)
    assert event_fields["ptid"] == "TEST001", "ptid should be present"
    assert event_fields["date"] == "2024-01-15", "date should be present"
    assert event_fields["visitnum"] == "01", "visitnum should be present"
    assert event_fields["module"] == "UDS", "module should be present"
    assert event_fields["packet"] == "I", "packet should be present"
    assert event_fields["adcid"] == 123, "adcid should be present"
    assert event_fields["naccid"] == "NACC123456", "naccid should be present"

    # Assert - Should include all DataIdentification fields
    expected_keys = {
        "ptid",
        "date",
        "visitnum",
        "module",
        "packet",
        "adcid",
        "naccid",
    }
    assert set(event_fields.keys()) == expected_keys, (
        "Should include all DataIdentification fields"
    )


def test_visit_metadata_inheritance_compatibility():
    """Test DataIdentification maintains compatibility with VisitKeys methods.

    **Feature: form-scheduler-event-logging-refactor,
      Property 9: Extended Visit Metadata Model**
    **Validates: Requirements 7.1, 7.2**

    DataIdentification should maintain compatibility with existing VisitKeys
    functionality.
    """
    # Arrange - Create test data
    test_record = {
        "ptid": "TEST001",
        "visitdate": "2024-01-15",
        "visitnum": "01",
        "module": "UDS",
        "adcid": 123,
    }

    # Act - Use VisitKeys.create_from class method
    visit_keys = VisitKeys.create_from(test_record, date_field="visitdate")

    # Act - Create DataIdentification from VisitKeys data
    visit_metadata = DataIdentification.from_visit_metadata(
        **visit_keys.model_dump(), packet="I"
    )

    # Assert - DataIdentification should have all VisitKeys data plus packet
    assert visit_metadata.ptid == visit_keys.ptid, "PTID should match"
    assert visit_metadata.date == visit_keys.date, "Date should match"
    assert visit_metadata.visitnum == visit_keys.visitnum, "Visit number should match"
    assert visit_metadata.module == visit_keys.module, "Module should match"
    assert visit_metadata.adcid == visit_keys.adcid, "ADCID should match"
    assert visit_metadata.packet == "I", "Packet should be added"

    # Assert - Should be able to use Pydantic methods
    metadata_dict = visit_metadata.model_dump(exclude_none=True)
    assert isinstance(metadata_dict, dict), "model_dump should work"
    assert "packet" in metadata_dict, "model_dump should include packet field"
