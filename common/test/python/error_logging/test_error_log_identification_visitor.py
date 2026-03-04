"""Tests for ErrorLogIdentificationVisitor log name prefix generation."""

from error_logging.error_logger import ErrorLogIdentificationVisitor
from nacc_common.data_identification import (
    DataIdentification,
    FormIdentification,
    ImageIdentification,
    ParticipantIdentification,
    VisitIdentification,
)


def test_form_data_from_visit():
    """Test log name prefix for form data from a visit.

    Note: Packet is excluded from filename per PR #372 review feedback.
    """
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345", naccid="NACC123"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="001"),
        data=FormIdentification(module="A1", packet="I"),
    )

    data_id.apply(visitor)

    # Format: {ptid}_{date}_{visitnum}_{module} (packet excluded)
    assert visitor.log_name_prefix == "12345_2024-01-15_001_a1"

    # Legacy prefix excludes visitnum (packet also excluded)
    assert visitor.legacy_log_name_prefix == "12345_2024-01-15_a1"


def test_form_data_from_visit_no_packet():
    """Test log name prefix for form data from visit without packet."""
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-01-15",
        visit=VisitIdentification(visitnum="002"),
        data=FormIdentification(module="B1", packet=None),
    )

    data_id.apply(visitor)

    # Format: {ptid}_{date}_{visitnum}_{module}
    assert visitor.log_name_prefix == "12345_2024-01-15_002_b1"
    assert visitor.legacy_log_name_prefix == "12345_2024-01-15_b1"


def test_form_data_outside_visit():
    """Test log name prefix for form data outside of a visit.

    Note: Packet is excluded from filename per PR #372 review feedback.
    """
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="67890"),
        date="2024-02-20",
        visit=None,  # No visit for non-visit forms
        data=FormIdentification(module="NP", packet="I"),
    )

    data_id.apply(visitor)

    # Format: {ptid}_{date}_{module} (no visitnum, packet excluded)
    assert visitor.log_name_prefix == "67890_2024-02-20_np"

    # Legacy format is the same (no visitnum, no packet)
    assert visitor.legacy_log_name_prefix == "67890_2024-02-20_np"


def test_form_data_outside_visit_no_packet():
    """Test log name prefix for form data outside visit without packet."""
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="11111"),
        date="2024-03-10",
        visit=None,
        data=FormIdentification(module="MILESTONE", packet=None),
    )

    data_id.apply(visitor)

    assert visitor.log_name_prefix == "11111_2024-03-10_milestone"
    assert visitor.legacy_log_name_prefix == "11111_2024-03-10_milestone"


def test_image_data():
    """Test log name prefix for image data."""
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="99999"),
        date="2024-04-05",
        visit=VisitIdentification(visitnum="003"),
        data=ImageIdentification(modality="MR"),
    )

    data_id.apply(visitor)

    # Format: {ptid}_{date}_{visitnum}_{modality}
    assert visitor.log_name_prefix == "99999_2024-04-05_003_mr"
    assert visitor.legacy_log_name_prefix == "99999_2024-04-05_mr"


def test_image_data_no_visit():
    """Test log name prefix for image data without visit."""
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="88888"),
        date="2024-05-15",
        visit=None,
        data=ImageIdentification(modality="PET"),
    )

    data_id.apply(visitor)

    assert visitor.log_name_prefix == "88888_2024-05-15_pet"
    assert visitor.legacy_log_name_prefix == "88888_2024-05-15_pet"


def test_ptid_normalization():
    """Test that ptid is normalized (leading zeros stripped)."""
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="00012345"),
        date="2024-06-01",
        visit=None,
        data=FormIdentification(module="A1", packet=None),
    )

    data_id.apply(visitor)

    # ptid should be normalized to "12345" (leading zeros removed)
    assert visitor.log_name_prefix == "12345_2024-06-01_a1"
    assert visitor.legacy_log_name_prefix == "12345_2024-06-01_a1"


def test_module_case_normalization():
    """Test that module is normalized to lowercase.

    Note: Packet is excluded from filename per PR #372 review feedback.
    """
    visitor = ErrorLogIdentificationVisitor()

    data_id = DataIdentification(
        participant=ParticipantIdentification(adcid=1, ptid="12345"),
        date="2024-07-01",
        visit=None,
        data=FormIdentification(module="A1", packet="F"),
    )

    data_id.apply(visitor)

    # Module should be lowercase, packet excluded
    # Format: {ptid}_{date}_{module}
    assert visitor.log_name_prefix == "12345_2024-07-01_a1"

    # Legacy format excludes packet
    assert visitor.legacy_log_name_prefix == "12345_2024-07-01_a1"


def test_empty_visitor_returns_none():
    """Test that visitor returns None when not populated."""
    visitor = ErrorLogIdentificationVisitor()

    # Before applying any data identification
    assert visitor.log_name_prefix is None
    assert visitor.legacy_log_name_prefix is None


if __name__ == "__main__":
    test_form_data_from_visit()
    test_form_data_from_visit_no_packet()
    test_form_data_outside_visit()
    test_form_data_outside_visit_no_packet()
    test_image_data()
    test_image_data_no_visit()
    test_ptid_normalization()
    test_module_case_normalization()
    test_empty_visitor_returns_none()
    print("✓ All tests passed!")
