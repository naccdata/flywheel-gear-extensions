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
    filename = template.instantiate(data_id)
    print(f"Form with visitnum and packet: {filename}")
    assert filename == "12345_001_2024-01-15_a1_i_qc-status.log"

    # Test 2: Form with packet but no visitnum (non-visit form)
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=None,  # No visit for non-visit forms
        data=FormIdentification(module="NP", packet="I"),
    )
    filename = template.instantiate(data_id)
    print(f"Form without visitnum: {filename}")
    assert filename == "12345_2024-01-15_np_i_qc-status.log"

    # Test 3: Form with visitnum but no packet
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet=None),
    )
    filename = template.instantiate(data_id)
    print(f"Form with visitnum, no packet: {filename}")
    assert filename == "12345_001_2024-01-15_a1_qc-status.log"

    # Test 4: Old format (no visitnum, no packet) - backward compatible
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=None,  # No visit for backward compatibility
        data=FormIdentification(module="A1", packet=None),
    )
    filename = template.instantiate(data_id)
    print(f"Old format (backward compatible): {filename}")
    assert filename == "12345_2024-01-15_a1_qc-status.log"

    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_new_filename_formats()
