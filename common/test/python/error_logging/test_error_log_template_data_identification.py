"""Tests for ErrorLogTemplate with DataIdentification."""

from error_logging.error_logger import ErrorLogTemplate
from nacc_common.data_identification import (
    DataIdentification,
    FormIdentification,
    ImageIdentification,
    ParticipantIdentification,
    VisitIdentification,
)


class TestErrorLogTemplateDataIdentification:
    """Test ErrorLogTemplate.instantiate_from_data_identification method."""

    def test_form_with_visitnum_and_packet(self):
        """Test filename generation for form with visitnum and packet.

        Note: Packet is excluded from filename per PR #372 review feedback.
        """
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(
                adcid=1, ptid="12345", naccid="NACC123"
            ),
            date="2024-01-15",
            visit=VisitIdentification(visitnum="001"),
            data=FormIdentification(module="A1", packet="I"),
        )

        filename = template.instantiate(data_id)

        # Format: {ptid}_{date}_{visitnum}_{module}_qc-status.log (packet excluded)
        assert filename == "12345_2024-01-15_001_a1_qc-status.log"

    def test_form_without_visitnum(self):
        """Test filename generation for non-visit form (no visitnum).

        Note: Packet is excluded from filename per PR #372 review feedback.
        """
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(adcid=1, ptid="12345"),
            date="2024-01-15",
            visit=None,  # No visit for non-visit forms
            data=FormIdentification(module="NP", packet="I"),
        )

        filename = template.instantiate(data_id)

        # Format: {ptid}_{date}_{module}_qc-status.log (no visitnum, packet excluded)
        assert filename == "12345_2024-01-15_np_qc-status.log"

    def test_form_with_visitnum_no_packet(self):
        """Test filename generation for form with visitnum but no packet."""
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(adcid=1, ptid="12345"),
            date="2024-01-15",
            visit=VisitIdentification(visitnum="001"),
            data=FormIdentification(module="A1", packet=None),
        )

        filename = template.instantiate(data_id)

        # Format: {ptid}_{date}_{visitnum}_{module}_qc-status.log
        assert filename == "12345_2024-01-15_001_a1_qc-status.log"

    def test_legacy_format_backward_compatible(self):
        """Test backward compatible legacy format (no visitnum, no packet)."""
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(adcid=1, ptid="12345"),
            date="2024-01-15",
            visit=None,  # No visit for legacy format
            data=FormIdentification(module="A1", packet=None),
        )

        filename = template.instantiate(data_id)

        assert filename == "12345_2024-01-15_a1_qc-status.log"

    def test_image_data(self):
        """Test filename generation for image data."""
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(adcid=1, ptid="12345"),
            date="2024-01-20",
            visit=None,  # No visit for image data
            data=ImageIdentification(modality="MR"),
        )

        # For images, modality should be in the module field
        data_id_with_module = data_id.model_copy(
            update={
                "data": FormIdentification(
                    module="MR", packet=None
                )  # Images use module field
            }
        )

        filename = template.instantiate(data_id_with_module)

        assert filename == "12345_2024-01-20_mr_qc-status.log"

    def test_missing_required_fields(self):
        """Test that validation errors are raised when required fields are
        missing."""
        import pytest
        from pydantic import ValidationError

        # Missing ptid - should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            DataIdentification(
                participant=ParticipantIdentification(adcid=1, ptid=None),
                date="2024-01-15",
                visit=VisitIdentification(visitnum="001"),
                data=FormIdentification(module="A1", packet="I"),
            )
        assert "ptid" in str(exc_info.value)

        # Missing date - should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            DataIdentification(
                participant=ParticipantIdentification(adcid=1, ptid="12345"),
                date=None,
                visit=VisitIdentification(visitnum="001"),
                data=FormIdentification(module="A1", packet="I"),
            )
        assert "date" in str(exc_info.value)

        # Missing module - should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            DataIdentification(
                participant=ParticipantIdentification(adcid=1, ptid="12345"),
                date="2024-01-15",
                visit=VisitIdentification(visitnum="001"),
                data=FormIdentification(module=None, packet="I"),
            )
        assert "module" in str(exc_info.value)

    def test_ptid_leading_zeros_stripped(self):
        """Test that leading zeros are stripped from ptid."""
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(adcid=1, ptid="00012345"),
            date="2024-01-15",
            visit=VisitIdentification(visitnum="001"),
            data=FormIdentification(module="A1", packet="I"),
        )

        filename = template.instantiate(data_id)

        # Leading zeros should be stripped, packet excluded
        # Format: {ptid}_{date}_{visitnum}_{module}_qc-status.log
        assert filename == "12345_2024-01-15_001_a1_qc-status.log"

    def test_module_and_packet_lowercase(self):
        """Test that module is converted to lowercase.

        Note: Packet is excluded from filename per PR #372 review feedback.
        """
        template = ErrorLogTemplate()
        data_id = DataIdentification(
            participant=ParticipantIdentification(adcid=1, ptid="12345"),
            date="2024-01-15",
            visit=VisitIdentification(visitnum="001"),
            data=FormIdentification(module="A1", packet="I"),
        )

        filename = template.instantiate(data_id)

        # Module should be lowercase, packet not in filename
        assert filename is not None
        assert "a1" in filename
        assert "A1" not in filename
        # Packet is not included in filename
        assert filename == "12345_2024-01-15_001_a1_qc-status.log"
