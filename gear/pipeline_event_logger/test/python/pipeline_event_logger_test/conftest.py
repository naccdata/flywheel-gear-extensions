"""Shared test fixtures for Pipeline Event Logger tests."""

from unittest.mock import Mock

import pytest
from event_capture.event_capture import VisitEventCapture
from pipeline_event_logger_test.test_factories import (
    build_data_identification_dict,
    build_qc_info,
    create_mock_file_entry,
    create_mock_project_adaptor,
)


@pytest.fixture
def upstream_gear_name() -> str:
    """Default upstream gear name for tests."""
    return "test-upstream-gear"


@pytest.fixture
def mock_file_entry(upstream_gear_name: str) -> Mock:
    """Create a mock FileEntry with valid QC and data_identification info."""
    info = build_qc_info(upstream_gear_name, status="PASS")
    info["data_identification"] = build_data_identification_dict()
    info["validated-timestamp"] = "2024-06-15 10:30:00"
    return create_mock_file_entry(info=info)


@pytest.fixture
def mock_project() -> Mock:
    """Create a mock ProjectAdaptor."""
    return create_mock_project_adaptor()


@pytest.fixture
def mock_event_capture() -> Mock:
    """Create a mock VisitEventCapture."""
    return Mock(spec=VisitEventCapture)


@pytest.fixture
def event_actions() -> dict[str, str]:
    """Default event actions mapping."""
    return {
        "pass": "pass-qc",
        "fail": "not-pass-qc",
    }
