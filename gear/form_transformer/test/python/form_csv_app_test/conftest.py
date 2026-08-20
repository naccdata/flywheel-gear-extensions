"""Shared test fixtures and factories for form_transformer tests."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple
from unittest.mock import MagicMock, Mock

import pytest
from configs.ingest_configs import ModuleConfigs
from event_capture.event_capture import VisitEventCapture
from flywheel.rest import ApiException
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
    metadata_copy_succeeds: bool = False,
) -> Tuple[CSVTransformVisitor, Mock]:
    """Create a CSVTransformVisitor with mocked dependencies for testing.

    Uses a mocked transformer that returns the row as-is (bypassing
    DateTransformer normalization) to allow testing edge cases.

    Args:
        metadata_copy_succeeds: If True, sets up the mock project so that
            __copy_downstream_gears_metadata succeeds (get_file returns a
            properly structured mock). If False, get_file returns None
            causing metadata copy to fail.

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

    # Mock ProjectAdaptor with group and label properties
    mock_project = Mock()
    mock_project.group = center_label
    mock_project.label = project_label

    if metadata_copy_succeeds:
        # Set up mock file that supports the metadata copy flow:
        # get_file returns a file with qc info so copy succeeds
        mock_file = Mock()
        mock_file.name = "test-error-log.json"
        mock_file.info = {"qc": {"form-transformer": {"status": "PASS"}}}
        mock_file.reload.return_value = mock_file
        mock_file.update_info.return_value = None
        mock_project.get_file.return_value = mock_file
    else:
        mock_project.get_file.return_value = None

    visitor = CSVTransformVisitor(
        id_column=FieldNames.NACCID,
        module=module,
        error_writer=error_writer,
        transformer_factory=mock_transformer_factory,
        preprocessor=mock_preprocessor,
        module_configs=module_configs,
        gear_name="form-transformer",
        project=mock_project,
        event_capture=event_capture,
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


def _create_np_module_configs() -> ModuleConfigs:
    """Create ModuleConfigs for a date-keyed module without visitnum."""
    module_configs = {
        "hierarchy_labels": {
            "session": {"template": "NP-RECORD-${npformdate}", "transform": "upper"},
            "acquisition": {"template": "${module}", "transform": "upper"},
            "filename": {
                "template": "${subject}_${session}_${acquisition}.json",
                "transform": "upper",
            },
        },
        "required_fields": ["ptid", "adcid", "npformdate", "module"],
        "initial_packets": ["NP"],
        "followup_packets": [],
        "versions": ["11.0"],
        "date_field": "npformdate",
        "preprocess_checks": ["duplicate-record"],
    }
    return ModuleConfigs.model_validate(module_configs)


def _create_visit_file_mock(
    *,
    forms_json: Optional[Dict[str, Any]] = None,
    qc: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
    name: str = "NACC000001_FORMS-VISIT-2_UDS.json",
    include_forms: bool = True,
    info: Optional[Dict[str, Any]] = None,
) -> Mock:
    """Create a mock acquisition file for an existing visit.

    Args:
        forms_json: contents of file.info.forms.json
        qc: contents of file.info.qc, omitted when None
        tags: file tags
        name: file name
        include_forms: whether to include the forms key in file.info
        info: use this file.info verbatim, ignoring the other arguments

    Returns:
        the mock file object
    """
    if info is None:
        info = {}
        if include_forms:
            info["forms"] = {"json": forms_json if forms_json is not None else {}}
        if qc is not None:
            info["qc"] = qc

    visit_file = Mock()
    visit_file.name = name
    visit_file.info = info
    visit_file.tags = list(tags) if tags else []
    visit_file.reload.return_value = visit_file
    return visit_file


@dataclass
class RejectionHarness:
    """Mocks for exercising the rejected-visit handling paths."""

    visitor: CSVTransformVisitor
    preprocessor: Mock
    project: Mock
    subject: Mock
    visit_file: Optional[Mock]


def _create_rejection_harness(
    *,
    visit_file: Optional[Mock] = None,
    subject_found: bool = True,
    lookup_error: bool = False,
    module_configs: Optional[ModuleConfigs] = None,
    module: str = "UDS",
    preprocess_result: bool = False,
    transform_result: bool = True,
) -> RejectionHarness:
    """Create a visitor whose acquisition lookup is fully controlled.

    Unlike `_create_visitor_with_mocks`, `find_acquisition_file` returns None
    by default rather than a truthy Mock, so the no-existing-visit path is the
    default.

    Args:
        visit_file: existing acquisition file to return from the lookup
        subject_found: whether the subject exists in the project
        lookup_error: whether the acquisition lookup raises an ApiException
        module_configs: module configs, defaults to the UDS style configs
        module: module label
        preprocess_result: return value of the mock preprocessor
        transform_result: whether the mock transformer returns the row

    Returns:
        the harness with the visitor and its mocks
    """
    configs = (
        module_configs
        if module_configs
        else _create_module_configs_with_duplicate_check()
    )
    error_writer = ListErrorWriter(container_id="test-id", fw_path="test/path")

    mock_preprocessor = Mock()
    mock_preprocessor.is_existing_visit.return_value = False
    mock_preprocessor.preprocess.return_value = preprocess_result

    mock_transformer = MagicMock()
    mock_transformer.transform.side_effect = (
        (lambda row, line_num: dict(row))
        if transform_result
        else (lambda row, line_num: None)
    )
    mock_transformer_factory = MagicMock()
    mock_transformer_factory.create.return_value = mock_transformer

    mock_subject = Mock()
    if lookup_error:
        mock_subject.find_acquisition_file.side_effect = ApiException(
            status=500, reason="boom"
        )
    else:
        mock_subject.find_acquisition_file.return_value = visit_file

    mock_project = Mock()
    mock_project.group = "adrc42"
    mock_project.label = "ingest-form"
    mock_project.find_subject.return_value = mock_subject if subject_found else None

    visitor = CSVTransformVisitor(
        id_column=FieldNames.NACCID,
        module=module,
        error_writer=error_writer,
        transformer_factory=mock_transformer_factory,
        preprocessor=mock_preprocessor,
        module_configs=configs,
        gear_name="form-transformer",
        project=mock_project,
    )

    return RejectionHarness(
        visitor=visitor,
        preprocessor=mock_preprocessor,
        project=mock_project,
        subject=mock_subject,
        visit_file=visit_file,
    )


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


@pytest.fixture
def create_rejection_harness() -> Callable[..., RejectionHarness]:
    """Fixture that returns the create_rejection_harness factory function."""
    return _create_rejection_harness


@pytest.fixture
def create_visit_file() -> Callable[..., Mock]:
    """Fixture that returns the create_visit_file_mock factory function."""
    return _create_visit_file_mock


@pytest.fixture
def np_module_configs() -> ModuleConfigs:
    """Fixture returning ModuleConfigs for a date-keyed module."""
    return _create_np_module_configs()
