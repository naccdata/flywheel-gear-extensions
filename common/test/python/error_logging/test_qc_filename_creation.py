"""Quick test to explore new QC filename generation."""

from error_logging.error_logger import ErrorLogTemplate
from nacc_common.data_identification import (
    DataIdentification,
    FormIdentification,
    ParticipantIdentification,
    VisitIdentification,
)


def test_new_filename_formats():
    """Test the new instantiate_from_data_identification method.

    Note: Packet is excluded from filename per PR #372 review feedback.
    Date comes before visitnum.
    """
    template = ErrorLogTemplate()

    # Test 1: Form with visitnum and packet (packet excluded from filename)
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345", naccid="NACC123"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet="I"),
    )
    filename = template.instantiate(data_id)
    print(f"Form with visitnum and packet: {filename}")
    # Format: {ptid}_{date}_{visitnum}_{module}_qc-status.log (packet excluded)
    assert filename == "12345_2024-01-15_001_a1_qc-status.log"

    # Test 2: Form with packet but no visitnum (packet excluded from filename)
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=None,  # No visit for non-visit forms
        data=FormIdentification(module="NP", packet="I"),
    )
    filename = template.instantiate(data_id)
    print(f"Form without visitnum: {filename}")
    # Format: {ptid}_{date}_{module}_qc-status.log (no visitnum, packet excluded)
    assert filename == "12345_2024-01-15_np_qc-status.log"

    # Test 3: Form with visitnum but no packet
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet=None),
    )
    filename = template.instantiate(data_id)
    print(f"Form with visitnum, no packet: {filename}")
    # Format: {ptid}_{date}_{visitnum}_{module}_qc-status.log
    assert filename == "12345_2024-01-15_001_a1_qc-status.log"

    # Test 4: Old format (no visitnum, no packet) - backward compatible
    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=None,  # No visit for backward compatibility
        data=FormIdentification(module="A1", packet=None),
    )
    filename = template.instantiate(data_id)
    print(f"Old format (backward compatible): {filename}")
    # Format: {ptid}_{date}_{module}_qc-status.log
    assert filename == "12345_2024-01-15_a1_qc-status.log"

    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_new_filename_formats()
