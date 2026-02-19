"""Quick test to explore new QC filename generation."""

from error_logging.error_logger import ErrorLogTemplate
from nacc_common.data_identification import (
    DataIdentification,
    FormIdentification,
    ParticipantIdentification,
    VisitIdentification,
)


def test_new_filename_formats():
    """Test the new instantiate_from_data_identification method."""
    template = ErrorLogTemplate()

    # Test 1: Form with visitnum and packet (most complete)
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345", naccid="NACC123"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet="I"),
    )
    filename = template.instantiate_from_data_identification(data_id)
    print(f"Form with visitnum and packet: {filename}")
    assert filename == "12345_001_2024-01-15_a1_i_qc-status.log"

    # Test 2: Form with packet but no visitnum (non-visit form)
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=None,  # No visit for non-visit forms
        data=FormIdentification(module="NP", packet="I"),
    )
    filename = template.instantiate_from_data_identification(data_id)
    print(f"Form without visitnum: {filename}")
    assert filename == "12345_2024-01-15_np_i_qc-status.log"

    # Test 3: Form with visitnum but no packet
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet=None),
    )
    filename = template.instantiate_from_data_identification(data_id)
    print(f"Form with visitnum, no packet: {filename}")
    assert filename == "12345_001_2024-01-15_a1_qc-status.log"

    # Test 4: Old format (no visitnum, no packet) - backward compatible
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=None,  # No visit for backward compatibility
        data=FormIdentification(module="A1", packet=None),
    )
    filename = template.instantiate_from_data_identification(data_id)
    print(f"Old format (backward compatible): {filename}")
    assert filename == "12345_2024-01-15_a1_qc-status.log"

    # Test 5: get_possible_filenames for lookup
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet="I"),
    )
    filenames = template.get_possible_filenames(data_id)
    print("\nPossible filenames for lookup:")
    for i, fn in enumerate(filenames, 1):
        print(f"  {i}. {fn}")

    # Should try new format first, then fallbacks
    assert filenames[0] == "12345_001_2024-01-15_a1_i_qc-status.log"
    assert "12345_2024-01-15_a1_qc-status.log" in filenames  # Legacy format

    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_new_filename_formats()
