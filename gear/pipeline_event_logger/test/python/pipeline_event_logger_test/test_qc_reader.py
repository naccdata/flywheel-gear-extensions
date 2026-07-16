"""Tests for QC reader error extraction with discriminated field mappings."""

import pytest
from pipeline_event_logger_app.qc_reader import (
    GearQC,
    GearQCResult,
    ListFieldMapping,
    NoneFieldMapping,
    QCErrorConfig,
    StringFieldMapping,
)

# ===========================================================================
# ListFieldMapping extraction
# ===========================================================================


class TestListFieldMapping:
    """Tests for extracting errors from list-of-dicts data."""

    def test_extracts_errors_from_list_of_dicts(self) -> None:
        """Maps each dict item to a FileError using field_mapping."""
        result = GearQCResult(
            name="dicom-validator",
            raw={
                "state": "FAIL",
                "data": [
                    {"name": "Tag (0008,0050) is missing", "slices": "all"},
                    {"name": "Tag (0010,0010) is missing", "slices": "all"},
                ],
            },
        )
        config = QCErrorConfig(
            check_name="dicom-validator",
            field_mapping=ListFieldMapping(
                type="list",
                message="name",
                error_code="dicom-validation",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 2
        assert errors[0].message == "Tag (0008,0050) is missing"
        assert errors[0].error_code == "dicom-validation"
        assert errors[0].error_type == "error"
        assert errors[1].message == "Tag (0010,0010) is missing"

    def test_resolves_error_type_from_source(self) -> None:
        """When error_type matches a key in source, uses source value."""
        result = GearQCResult(
            name="jsonschema-validation",
            raw={
                "state": "FAIL",
                "data": [
                    {
                        "error_message": "'MR' is required",
                        "error_type": "warning",
                        "error_value": ["MR", "PT"],
                    },
                ],
            },
        )
        config = QCErrorConfig(
            check_name="jsonschema-validation",
            field_mapping=ListFieldMapping(
                type="list",
                message="error_message",
                error_type="error_type",
                error_code="jsonschema-validation",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].message == "'MR' is required"
        assert errors[0].error_type == "warning"
        assert errors[0].error_code == "jsonschema-validation"

    def test_literal_error_code_when_not_in_source(self) -> None:
        """When error_code is not a key in source, uses it as literal."""
        result = GearQCResult(
            name="validator",
            raw={
                "state": "FAIL",
                "data": [{"msg": "bad value"}],
            },
        )
        config = QCErrorConfig(
            check_name="validator",
            field_mapping=ListFieldMapping(
                type="list",
                message="msg",
                error_code="my-literal-code",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].error_code == "my-literal-code"

    def test_empty_list_returns_no_errors(self) -> None:
        """Empty data list produces no errors."""
        result = GearQCResult(
            name="validation",
            raw={"state": "PASS", "data": []},
        )
        config = QCErrorConfig(
            check_name="validation",
            field_mapping=ListFieldMapping(type="list", message="message"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0

    def test_non_list_data_returns_no_errors(self) -> None:
        """Non-list data with list mapping produces no errors."""
        result = GearQCResult(
            name="validation",
            raw={"state": "FAIL", "data": "some string"},
        )
        config = QCErrorConfig(
            check_name="validation",
            field_mapping=ListFieldMapping(type="list", message="message"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0

    def test_null_data_returns_no_errors(self) -> None:
        """Null data with list mapping produces no errors."""
        result = GearQCResult(
            name="validation",
            raw={"state": "FAIL", "data": None},
        )
        config = QCErrorConfig(
            check_name="validation",
            field_mapping=ListFieldMapping(type="list", message="message"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0

    def test_skips_non_dict_items_in_list(self) -> None:
        """Non-dict items in the list are skipped."""
        result = GearQCResult(
            name="validation",
            raw={
                "state": "FAIL",
                "data": [
                    {"message": "real error"},
                    "not a dict",
                    42,
                    {"message": "another error"},
                ],
            },
        )
        config = QCErrorConfig(
            check_name="validation",
            field_mapping=ListFieldMapping(type="list", message="message"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 2
        assert errors[0].message == "real error"
        assert errors[1].message == "another error"

    def test_value_field_extracted_when_configured(self) -> None:
        """Optional value field is extracted when specified."""
        result = GearQCResult(
            name="validation",
            raw={
                "state": "FAIL",
                "data": [
                    {"message": "bad value", "value": "DX"},
                ],
            },
        )
        config = QCErrorConfig(
            check_name="validation",
            field_mapping=ListFieldMapping(
                type="list", message="message", value="value"
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].value == "DX"

    def test_custom_data_key(self) -> None:
        """Uses configured data_key instead of default 'data'."""
        result = GearQCResult(
            name="validation",
            raw={
                "state": "FAIL",
                "errors": [{"msg": "found here"}],
                "data": [{"msg": "not here"}],
            },
        )
        config = QCErrorConfig(
            check_name="validation",
            data_key="errors",
            field_mapping=ListFieldMapping(type="list", message="msg"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].message == "found here"


# ===========================================================================
# StringFieldMapping extraction
# ===========================================================================


class TestStringFieldMapping:
    """Tests for extracting errors from string data."""

    def test_string_data_becomes_error_message(self) -> None:
        """String data is used directly as the error message."""
        result = GearQCResult(
            name="slice_consistency",
            raw={
                "state": "FAIL",
                "data": "Inconsistent slice intervals. Majority are ~1.0mm(56)",
            },
        )
        config = QCErrorConfig(
            check_name="slice_consistency",
            field_mapping=StringFieldMapping(
                type="string",
                error_code="slice-consistency",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].message == (
            "Inconsistent slice intervals. Majority are ~1.0mm(56)"
        )
        assert errors[0].error_code == "slice-consistency"
        assert errors[0].error_type == "error"

    def test_custom_error_type(self) -> None:
        """Uses configured error_type on synthesized error."""
        result = GearQCResult(
            name="bed_moving",
            raw={"state": "FAIL", "data": "Bed moved during scan"},
        )
        config = QCErrorConfig(
            check_name="bed_moving",
            field_mapping=StringFieldMapping(
                type="string",
                error_type="warning",
                error_code="bed-moving",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].error_type == "warning"

    def test_null_data_returns_no_errors(self) -> None:
        """Null data with string mapping produces no errors."""
        result = GearQCResult(
            name="slice_consistency",
            raw={"state": "PASS", "data": None},
        )
        config = QCErrorConfig(
            check_name="slice_consistency",
            field_mapping=StringFieldMapping(
                type="string", error_code="slice-consistency"
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0

    def test_list_data_returns_no_errors(self) -> None:
        """List data with string mapping produces no errors."""
        result = GearQCResult(
            name="check",
            raw={"state": "FAIL", "data": [{"msg": "something"}]},
        )
        config = QCErrorConfig(
            check_name="check",
            field_mapping=StringFieldMapping(type="string", error_code="check"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0


# ===========================================================================
# NoneFieldMapping extraction
# ===========================================================================


class TestNoneFieldMapping:
    """Tests for synthesizing errors when data is null."""

    def test_failed_check_with_null_data_synthesizes_message(self) -> None:
        """FAIL state with null data synthesizes '{check_name} failed'."""
        result = GearQCResult(
            name="check_zero_byte",
            raw={"state": "FAIL", "data": None},
        )
        config = QCErrorConfig(
            check_name="check_zero_byte",
            field_mapping=NoneFieldMapping(
                type="none",
                error_code="zero-byte",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].message == "check_zero_byte failed"
        assert errors[0].error_code == "zero-byte"
        assert errors[0].error_type == "error"

    def test_in_review_state_synthesizes_message(self) -> None:
        """IN REVIEW state with null data also synthesizes a message."""
        result = GearQCResult(
            name="embedded_localizer",
            raw={"state": "IN REVIEW", "data": None},
        )
        config = QCErrorConfig(
            check_name="embedded_localizer",
            field_mapping=NoneFieldMapping(
                type="none",
                error_code="embedded-localizer",
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].message == "embedded_localizer failed"

    def test_pass_state_with_null_data_returns_no_errors(self) -> None:
        """PASS state with null data produces no errors."""
        result = GearQCResult(
            name="check_zero_byte",
            raw={"state": "PASS", "data": None},
        )
        config = QCErrorConfig(
            check_name="check_zero_byte",
            field_mapping=NoneFieldMapping(type="none", error_code="zero-byte"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0

    def test_missing_data_key_with_fail_state(self) -> None:
        """Missing data key (implicitly null) with FAIL state synthesizes."""
        result = GearQCResult(
            name="series_consistency",
            raw={"state": "FAIL"},
        )
        config = QCErrorConfig(
            check_name="series_consistency",
            field_mapping=NoneFieldMapping(
                type="none", error_code="series-consistency"
            ),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 1
        assert errors[0].message == "series_consistency failed"


# ===========================================================================
# Check name matching
# ===========================================================================


class TestCheckNameMatching:
    """Tests that extraction only happens when check_name matches."""

    def test_mismatched_check_name_returns_empty(self) -> None:
        """Config targeting a different check returns no errors."""
        result = GearQCResult(
            name="dicom-validator",
            raw={"state": "FAIL", "data": [{"name": "error"}]},
        )
        config = QCErrorConfig(
            check_name="other-check",
            field_mapping=ListFieldMapping(type="list", message="name"),
        )

        errors = result.extract_errors(config)

        assert len(errors) == 0


# ===========================================================================
# GearQC.extract_errors integration
# ===========================================================================


class TestGearQCExtractErrors:
    """Tests for GearQC-level error extraction across multiple configs."""

    def test_aggregates_errors_from_multiple_configs(self) -> None:
        """Combines errors from multiple check results."""
        gear_qc = GearQC(
            gear_name="dicom-qc",
            raw={
                "job_info": {"version": "0.5.9"},
                "dicom-validator": {
                    "state": "FAIL",
                    "data": [{"name": "Tag missing", "slices": "all"}],
                },
                "slice_consistency": {
                    "state": "FAIL",
                    "data": "Inconsistent intervals",
                },
                "check_zero_byte": {
                    "state": "FAIL",
                    "data": None,
                },
                "embedded_localizer": {
                    "state": "PASS",
                    "data": None,
                },
            },
        )
        configs = [
            QCErrorConfig(
                check_name="dicom-validator",
                field_mapping=ListFieldMapping(
                    type="list", message="name", error_code="dicom-validation"
                ),
            ),
            QCErrorConfig(
                check_name="slice_consistency",
                field_mapping=StringFieldMapping(
                    type="string", error_code="slice-consistency"
                ),
            ),
            QCErrorConfig(
                check_name="check_zero_byte",
                field_mapping=NoneFieldMapping(type="none", error_code="zero-byte"),
            ),
            QCErrorConfig(
                check_name="embedded_localizer",
                field_mapping=NoneFieldMapping(
                    type="none", error_code="embedded-localizer"
                ),
            ),
        ]

        errors = gear_qc.extract_errors(configs)

        # dicom-validator: 1 list error
        # slice_consistency: 1 string error
        # check_zero_byte: 1 synthesized error (FAIL + null)
        # embedded_localizer: 0 (PASS + null)
        assert len(errors) == 3
        assert errors[0].message == "Tag missing"
        assert errors[0].error_code == "dicom-validation"
        assert errors[1].message == "Inconsistent intervals"
        assert errors[1].error_code == "slice-consistency"
        assert errors[2].message == "check_zero_byte failed"
        assert errors[2].error_code == "zero-byte"

    def test_no_configs_returns_empty(self) -> None:
        """No error_configs returns empty list."""
        gear_qc = GearQC(
            gear_name="dicom-qc",
            raw={
                "dicom-validator": {"state": "FAIL", "data": [{"name": "err"}]},
            },
        )

        errors = gear_qc.extract_errors(None)

        assert len(errors) == 0

    def test_config_for_missing_check_is_skipped(self) -> None:
        """Config targeting a non-existent check is silently skipped."""
        gear_qc = GearQC(
            gear_name="dicom-qc",
            raw={
                "dicom-validator": {
                    "state": "PASS",
                    "data": [],
                },
            },
        )
        configs = [
            QCErrorConfig(
                check_name="nonexistent",
                field_mapping=NoneFieldMapping(type="none", error_code="x"),
            ),
        ]

        errors = gear_qc.extract_errors(configs)

        assert len(errors) == 0


# ===========================================================================
# QCErrorConfig model validation
# ===========================================================================


class TestQCErrorConfigValidation:
    """Tests that QCErrorConfig correctly parses discriminated field
    mappings."""

    def test_parses_list_mapping_from_dict(self) -> None:
        """Validates list field mapping from raw dict."""
        config = QCErrorConfig.model_validate(
            {
                "check_name": "validation",
                "field_mapping": {
                    "type": "list",
                    "message": "message",
                    "error_type": "type",
                    "error_code": "code",
                },
            }
        )

        assert isinstance(config.field_mapping, ListFieldMapping)
        assert config.field_mapping.message == "message"

    def test_parses_string_mapping_from_dict(self) -> None:
        """Validates string field mapping from raw dict."""
        config = QCErrorConfig.model_validate(
            {
                "check_name": "slice_consistency",
                "field_mapping": {
                    "type": "string",
                    "error_code": "slice-consistency",
                },
            }
        )

        assert isinstance(config.field_mapping, StringFieldMapping)
        assert config.field_mapping.error_code == "slice-consistency"

    def test_parses_none_mapping_from_dict(self) -> None:
        """Validates none field mapping from raw dict."""
        config = QCErrorConfig.model_validate(
            {
                "check_name": "check_zero_byte",
                "field_mapping": {
                    "type": "none",
                    "error_code": "zero-byte",
                },
            }
        )

        assert isinstance(config.field_mapping, NoneFieldMapping)
        assert config.field_mapping.error_code == "zero-byte"

    def test_invalid_type_raises_validation_error(self) -> None:
        """Invalid type discriminator raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QCErrorConfig.model_validate(
                {
                    "check_name": "check",
                    "field_mapping": {
                        "type": "invalid",
                        "message": "msg",
                    },
                }
            )
