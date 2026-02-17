"""Test for DataIdentification serialization without visitnum field.

This test reproduces the issue where forms without visit numbers
cause a KeyError during serialization.

The issue occurs when CSV data doesn't have a visitnum column at all,
so row.get(FieldNames.VISITNUM) returns None, and then during serialization
the pop() operation fails because the key might not exist in the data dict.
"""

from nacc_common.data_identification import DataIdentification


def test_visit_metadata_without_visitnum():
    """Test that DataIdentification can be serialized without visitnum field.

    Simulates the case where CSV data doesn't have a visitnum column.
    """
    # Arrange - Create DataIdentification without visitnum (common for some forms)
    # This simulates: row.get(FieldNames.VISITNUM) returning None
    visit_metadata = DataIdentification.from_visit_metadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum=None,  # Some forms don't have visit numbers
        module="UDS",
        packet="I",
        adcid=123,
    )

    # Act - Serialize the metadata (this should not raise KeyError)
    event_fields = visit_metadata.model_dump()

    # Assert - Should serialize successfully with visitnum as None
    assert event_fields["visitnum"] is None
    assert event_fields["date"] == "2024-01-15"
    assert event_fields["ptid"] == "TEST001"


def test_visit_metadata_missing_visitnum_key():
    """Test that DataIdentification handles missing visitnum key during
    creation."""
    # Arrange - Create DataIdentification without providing visitnum at all
    visit_metadata = DataIdentification.from_visit_metadata(
        ptid="TEST001",
        date="2024-01-15",
        module="UDS",
        packet="I",
    )

    # Act - Serialize the metadata
    event_fields = visit_metadata.model_dump()

    # Assert - Should serialize successfully with visitnum as None
    assert event_fields["visitnum"] is None


def test_visit_metadata_serialization_modes():
    """Test DataIdentification serialization in different modes."""
    # Arrange
    visit_metadata = DataIdentification.from_visit_metadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum=None,
        module="UDS",
    )

    # Act & Assert - Test different serialization modes
    # Default mode (python)
    python_dict = visit_metadata.model_dump()
    assert "visitnum" in python_dict
    assert python_dict["visitnum"] is None

    # JSON mode
    json_dict = visit_metadata.model_dump(mode="json")
    assert "visitnum" in json_dict
    assert json_dict["visitnum"] is None


def test_visit_metadata_exclude_none_serialization():
    """Test DataIdentification serialization with exclude_none=True.

    This reproduces the KeyError when visitnum is None and exclude_none
    is used.
    """
    # Arrange
    visit_metadata = DataIdentification.from_visit_metadata(
        ptid="TEST001",
        date="2024-01-15",
        visitnum=None,  # This will be excluded when exclude_none=True
        module="UDS",
    )

    # Act - This should not raise KeyError
    result = visit_metadata.model_dump(exclude_none=True)

    # Assert - visitnum should not be in result since it was None
    assert "visitnum" not in result or result.get("visitnum") is None
    assert "date" in result
    assert result["date"] == "2024-01-15"
