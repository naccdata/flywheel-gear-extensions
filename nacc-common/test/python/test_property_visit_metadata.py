"""Property test for VisitMetadata model.

**Feature: form-scheduler-event-logging-refactor,
  Property 9: Extended Visit Metadata Model**
**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
"""

from typing import Any, Dict

from hypothesis import given, settings
from hypothesis import strategies as st
from nacc_common.error_models import VisitKeys, VisitMetadata


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
    """Generate random VisitMetadata data."""
    visit_keys_data = draw(visit_keys_strategy())
    packet = draw(st.one_of(st.none(), st.text(min_size=1, max_size=5)))

    return {**visit_keys_data, "packet": packet}


@given(visit_data=visit_metadata_strategy())
@settings(max_examples=100)
def test_visit_metadata_extends_visit_keys(visit_data: Dict[str, Any]):
    """Property test: VisitMetadata extends VisitKeys with packet field.

    **Feature: form-scheduler-event-logging-refactor,
      Property 9: Extended Visit Metadata Model**
    **Validates: Requirements 7.1, 7.2**

    For any visit data, VisitMetadata should extend VisitKeys with an optional
    packet field and maintain all VisitKeys functionality.
    """
    # Act - Create VisitMetadata instance
    visit_metadata = VisitMetadata(**visit_data)

    # Assert - VisitMetadata should be an instance of VisitKeys
    assert isinstance(visit_metadata, VisitKeys), (
        "VisitMetadata should extend VisitKeys"
    )

    # Assert - VisitMetadata should have all VisitKeys fields
    assert hasattr(visit_metadata, "adcid"), "VisitMetadata should have adcid field"
    assert hasattr(visit_metadata, "ptid"), "VisitMetadata should have ptid field"
    assert hasattr(visit_metadata, "visitnum"), (
        "VisitMetadata should have visitnum field"
    )
    assert hasattr(visit_metadata, "module"), "VisitMetadata should have module field"
    assert hasattr(visit_metadata, "date"), "VisitMetadata should have date field"
    assert hasattr(visit_metadata, "naccid"), "VisitMetadata should have naccid field"

    # Assert - VisitMetadata should have packet field
    assert hasattr(visit_metadata, "packet"), "VisitMetadata should have packet field"
    assert visit_metadata.packet == visit_data.get("packet"), (
        "VisitMetadata packet should match input"
    )

    # Assert - All VisitKeys fields should match input
    assert visit_metadata.adcid == visit_data.get("adcid"), (
        "VisitMetadata adcid should match input"
    )
    assert visit_metadata.ptid == visit_data.get("ptid"), (
        "VisitMetadata ptid should match input"
    )
    assert visit_metadata.visitnum == visit_data.get("visitnum"), (
        "VisitMetadata visitnum should match input"
    )
    assert visit_metadata.module == visit_data.get("module"), (
        "VisitMetadata module should match input"
    )
    assert visit_metadata.date == visit_data.get("date"), (
        "VisitMetadata date should match input"
    )
    assert visit_metadata.naccid == visit_data.get("naccid"), (
        "VisitMetadata naccid should match input"
    )


@given(visit_data=visit_metadata_strategy())
@settings(max_examples=100)
def test_visit_metadata_to_visit_event_fields_mapping(visit_data: Dict[str, Any]):
    """Property test: VisitMetadata serialization maps field names correctly.

          **Feature: form-scheduler-event-logging-refactor,
        Property 9: Extended Visit Metadata Model**
          **Validates: Requirements 7.3, 7.4, 7.5**

          For any VisitMetadata instance, model serialization should map field names
          correctly for
    VisitEvent creation.and include all required fields.
    """
    # Arrange - Create VisitMetadata instance
    visit_metadata = VisitMetadata(**visit_data)

    # Act - Get field mapping for VisitEvent using model serialization
    event_fields = visit_metadata.model_dump()

    # Assert - Should return a dictionary
    assert isinstance(event_fields, dict), "model_dump should return a dictionary"

    # Assert - Should have correct field name mappings
    # (date -> visit_date, visitnum -> visit_number)
    expected_fields = [
        "ptid",
        "visit_date",
        "visit_number",
        "module",
        "packet",
        "adcid",
        "naccid",
    ]
    for field in expected_fields:
        assert field in event_fields, f"Event fields should contain {field}"

    # Assert - Should NOT have the original field names that were mapped
    assert "date" not in event_fields, (
        "Original 'date' field should be mapped to 'visit_date'"
    )
    assert "visitnum" not in event_fields, (
        "Original 'visitnum' field should be mapped to 'visit_number'"
    )

    # Assert - Field mappings should be correct
    assert event_fields["ptid"] == visit_metadata.ptid, "ptid should map directly"
    assert event_fields["visit_date"] == visit_metadata.date, (
        "date should map to visit_date"
    )
    assert event_fields["visit_number"] == visit_metadata.visitnum, (
        "visitnum should map to visit_number"
    )
    assert event_fields["module"] == visit_metadata.module, "module should map directly"
    assert event_fields["packet"] == visit_metadata.packet, "packet should map directly"
    assert event_fields["adcid"] == visit_metadata.adcid, "adcid should map directly"
    assert event_fields["naccid"] == visit_metadata.naccid, "naccid should map directly"


def test_visit_metadata_with_packet_field():
    """Test VisitMetadata with packet field for form packet information.

      **Feature: form-scheduler-event-logging-refactor,
    Property 9: Extended Visit Metadata Model**
      **Validates: Requirements 7.1, 7.2**

      VisitMetadata should include an optional packet field for form packet information.
    """
    # Arrange & Act - Create VisitMetadata with packet
    visit_metadata = VisitMetadata(
        ptid="TEST001", date="2024-01-15", visitnum="01", module="UDS", packet="I"
    )

    # Assert - Packet field should be available and correct
    assert visit_metadata.packet == "I", "VisitMetadata should store packet information"

    # Act - Create VisitMetadata without packet (should default to None)
    visit_metadata_no_packet = VisitMetadata(
        ptid="TEST002", date="2024-01-16", visitnum="02", module="UDS"
    )

    # Assert - Packet should default to None
    assert visit_metadata_no_packet.packet is None, (
        "VisitMetadata packet should default to None"
    )


def test_visit_metadata_field_name_mapping():
    """Test VisitMetadata field name mapping for VisitEvent creation.

          **Feature: form-scheduler-event-logging-refactor,
            Property 9: Extended Visit Metadata Model**
          **Validates: Requirements 7.3, 7.4, 7.5**

          VisitMetadata serialization should map field names correctly for
    VisitEvent creation.
    """
    # Arrange - Create VisitMetadata with all fields
    visit_metadata = VisitMetadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum="01",
        module="UDS",
        packet="I",
        adcid=123,
        naccid="NACC123456",
    )

    # Act - Get field mapping using model serialization
    event_fields = visit_metadata.model_dump()

    # Assert - Field name mappings should be correct
    assert event_fields["ptid"] == "TEST001", "ptid should map directly"
    assert event_fields["visit_date"] == "2024-01-15", "date should map to visit_date"
    assert event_fields["visit_number"] == "01", "visitnum should map to visit_number"
    assert event_fields["module"] == "UDS", "module should map directly"
    assert event_fields["packet"] == "I", "packet should map directly"
    assert event_fields["adcid"] == 123, "adcid should map directly"
    assert event_fields["naccid"] == "NACC123456", "naccid should map directly"

    # Assert - Should NOT have the original field names that were mapped
    assert "date" not in event_fields, (
        "Original 'date' field should be mapped to 'visit_date'"
    )
    assert "visitnum" not in event_fields, (
        "Original 'visitnum' field should be mapped to 'visit_number'"
    )

    # Assert - Should include all VisitMetadata fields with proper mapping
    expected_keys = {
        "ptid",
        "visit_date",
        "visit_number",
        "module",
        "packet",
        "adcid",
        "naccid",
    }
    assert set(event_fields.keys()) == expected_keys, (
        "Should include all VisitMetadata fields with proper mapping"
    )


def test_visit_metadata_inheritance_compatibility():
    """Test VisitMetadata maintains compatibility with VisitKeys methods.

    **Feature: form-scheduler-event-logging-refactor,
      Property 9: Extended Visit Metadata Model**
    **Validates: Requirements 7.1, 7.2**

    VisitMetadata should maintain compatibility with existing VisitKeys functionality.
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

    # Act - Create VisitMetadata from VisitKeys data
    visit_metadata = VisitMetadata(**visit_keys.model_dump(), packet="I")

    # Assert - VisitMetadata should have all VisitKeys data plus packet
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
