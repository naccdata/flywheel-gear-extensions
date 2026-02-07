"""Test for VisitMetadata serialization without visitnum field.

This test reproduces the issue where forms without visit numbers
cause a KeyError during serialization.

The issue occurs when CSV data doesn't have a visitnum column at all,
so row.get(FieldNames.VISITNUM) returns None, and then during serialization
the pop() operation fails because the key might not exist in the data dict.
"""

from nacc_common.error_models import VisitMetadata


def test_visit_metadata_without_visitnum():
    """Test that VisitMetadata can be serialized without visitnum field.

    Simulates the case where CSV data doesn't have a visitnum column.
    """
    # Arrange - Create VisitMetadata without visitnum (common for some forms)
    # This simulates: row.get(FieldNames.VISITNUM) returning None
    visit_metadata = VisitMetadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum=None,  # Some forms don't have visit numbers
        module="UDS",
        packet="I",
        adcid=123,
    )

    # Act - Serialize the metadata (this should not raise KeyError)
    event_fields = visit_metadata.model_dump()

    # Assert - Should serialize successfully with visit_number as None
    assert event_fields["visit_number"] is None
    assert event_fields["visit_date"] == "2024-01-15"
    assert event_fields["ptid"] == "TEST001"


def test_visit_metadata_missing_visitnum_key():
    """Test that VisitMetadata handles missing visitnum key during creation."""
    # Arrange - Create VisitMetadata without providing visitnum at all
    visit_metadata = VisitMetadata(
        ptid="TEST001",
        date="2024-01-15",
        module="UDS",
        packet="I",
    )

    # Act - Serialize the metadata
    event_fields = visit_metadata.model_dump()

    # Assert - Should serialize successfully with visit_number as None
    assert event_fields["visit_number"] is None
    assert "visitnum" not in event_fields  # Original field name should be mapped


def test_visit_metadata_serialization_modes():
    """Test VisitMetadata serialization in different modes."""
    # Arrange
    visit_metadata = VisitMetadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum=None,
        module="UDS",
    )

    # Act & Assert - Test different serialization modes
    # Default mode (python)
    python_dict = visit_metadata.model_dump()
    assert "visit_number" in python_dict
    assert python_dict["visit_number"] is None

    # JSON mode
    json_dict = visit_metadata.model_dump(mode="json")
    assert "visit_number" in json_dict
    assert json_dict["visit_number"] is None


def test_visit_metadata_exclude_none_serialization():
    """Test VisitMetadata serialization with exclude_none=True.

    This reproduces the KeyError when visitnum is None and exclude_none
    is used.
    """
    # Arrange
    visit_metadata = VisitMetadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum=None,  # This will be excluded when exclude_none=True
        module="UDS",
    )

    # Act - This should not raise KeyError
    result = visit_metadata.model_dump(exclude_none=True)

    # Assert - visit_number should not be in result since it was None
    assert "visit_number" not in result or result.get("visit_number") is None
    assert "visit_date" in result
    assert result["visit_date"] == "2024-01-15"
