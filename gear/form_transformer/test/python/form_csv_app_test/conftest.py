"""Shared test fixtures and factories for form_transformer tests."""

from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple
from unittest.mock import MagicMock, Mock

import pytest
from configs.ingest_configs import ModuleConfigs
from event_capture.event_capture import VisitEventCapture
from form_csv_app.main import CSVTransformVisitor
from nacc_common.field_names import FieldNames
from outputs.error_writer import ListErrorWriter


def _create_module_configs_with_duplicate_check() -> ModuleConfigs:
    """Create ModuleConfigs that includes duplicate-record preprocess check."""
    module_configs = {
        "hierarchy_labels": {
            "session": {"template": "FORMS-VISIT-${visitnum}", "transform": "upper"},
            "acquisition": {"template": "${module}", "transform": "upper"},
            "filename": {
                "template": "${subject}_${session}_${acquisition}.json",
                "transform": "upper",
            },
        },
        "required_fields": [
            "ptid",
            "adcid",
            "visitnum",
            "visitdate",
            "module",
        ],
        "initial_packets": ["I"],
        "followup_packets": ["F"],
        "versions": ["4.0"],
        "date_field": "visitdate",
        "preprocess_checks": [
            "duplicate-record",
        ],
    }
    return ModuleConfigs.model_validate(module_configs)


def _create_valid_row(
    ptid: str = "110001",
    visitdate: str = "2024-03-15",
    module: str = "UDS",
    visitnum: str = "2",
    adcid: int = 42,
    naccid: str = "NACC000001",
) -> Dict[str, Any]:
    """Create a valid CSV row with all expected fields."""
    return {
        FieldNames.PTID: ptid,
        FieldNames.DATE_COLUMN: visitdate,
        FieldNames.MODULE: module,
        FieldNames.VISITNUM: visitnum,
        FieldNames.ADCID: adcid,
        FieldNames.NACCID: naccid,
    }


def _create_visitor_with_mocks(
    *,
    event_capture: Optional[VisitEventCapture] = None,
    center_label: str = "adrc42",
    project_label: str = "ingest-form",
    timestamp: Optional[datetime] = None,
    is_existing_visit: bool = False,
) -> Tuple[CSVTransformVisitor, Mock]:
    """Create a CSVTransformVisitor with mocked dependencies for testing.

    Uses a mocked transformer that returns the row as-is (bypassing
    DateTransformer normalization) to allow testing edge cases.

    Returns the visitor and the mock preprocessor.
    """
    module = "UDS"
    module_configs = _create_module_configs_with_duplicate_check()
    error_writer = ListErrorWriter(container_id="test-id", fw_path="test/path")

    # Use a mock preprocessor so we can control is_existing_visit behavior
    mock_preprocessor = Mock()
    mock_preprocessor.is_existing_visit.return_value = is_existing_visit
    mock_preprocessor.preprocess.return_value = True

    # Use a mock transformer factory that returns rows as-is
    # This bypasses DateTransformer so we can test __capture_duplicate_event
    # with invalid dates that would normally be caught by the transformer
    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = lambda row, line_num: dict(row)
    mock_transformer_factory = MagicMock()
    mock_transformer_factory.create.return_value = mock_transformer

    visitor = CSVTransformVisitor(
        id_column=FieldNames.NACCID,
        module=module,
        error_writer=error_writer,
        transformer_factory=mock_transformer_factory,
        preprocessor=mock_preprocessor,
        module_configs=module_configs,
        gear_name="form-transformer",
        project=None,
        event_capture=event_capture,
        center_label=center_label,
        project_label=project_label,
        timestamp=timestamp,
    )

    header = [
        FieldNames.NACCID,
        FieldNames.DATE_COLUMN,
        FieldNames.MODULE,
        FieldNames.VISITNUM,
        FieldNames.ADCID,
        FieldNames.PTID,
    ]
    assert visitor.visit_header(header)

    return visitor, mock_preprocessor


# Type alias for the factory callables exposed as fixtures
CreateValidRowFactory = Callable[..., Dict[str, Any]]
CreateVisitorFactory = Callable[..., Tuple[CSVTransformVisitor, Mock]]


@pytest.fixture
def create_valid_row() -> CreateValidRowFactory:
    """Fixture that returns the create_valid_row factory function."""
    return _create_valid_row


@pytest.fixture
def create_visitor_with_mocks() -> CreateVisitorFactory:
    """Fixture that returns the create_visitor_with_mocks factory function."""
    return _create_visitor_with_mocks
