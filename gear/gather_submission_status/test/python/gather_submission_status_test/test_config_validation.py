"""Tests for reload_workers validation in run.py.

Validates: Requirements 5.2 / Property 5: Non-Positive reload_workers Rejected
"""

from unittest.mock import Mock, patch

import pytest
from gather_submission_status_app.run import GatherSubmissionStatusVisitor
from gear_execution.gear_execution import GearExecutionError


@pytest.fixture
def mock_context():
    """Create a mock GearContext with configurable options."""
    context = Mock()
    context.config.opts = {
        "output_file": "test.csv",
        "admin_group": "nacc",
        "project_names": "ingest-form",
        "modules": "UDS,FTLD",
        "study_id": "adrc",
        "query_type": "status",
    }
    return context


@patch("gather_submission_status_app.run.InputFileWrapper.create")
@patch("gather_submission_status_app.run.GearBotClient.create")
def test_reload_workers_zero_raises(mock_bot_create, mock_input_create, mock_context):
    """Test that reload_workers=0 raises GearExecutionError."""
    mock_bot_create.return_value = Mock()
    mock_input_create.return_value = Mock()
    mock_context.config.opts["reload_workers"] = 0

    with pytest.raises(
        GearExecutionError, match="reload_workers must be a positive integer"
    ):
        GatherSubmissionStatusVisitor.create(mock_context)


@patch("gather_submission_status_app.run.InputFileWrapper.create")
@patch("gather_submission_status_app.run.GearBotClient.create")
def test_reload_workers_negative_raises(
    mock_bot_create, mock_input_create, mock_context
):
    """Test that reload_workers=-5 raises GearExecutionError."""
    mock_bot_create.return_value = Mock()
    mock_input_create.return_value = Mock()
    mock_context.config.opts["reload_workers"] = -5

    with pytest.raises(
        GearExecutionError, match="reload_workers must be a positive integer"
    ):
        GatherSubmissionStatusVisitor.create(mock_context)


@patch("gather_submission_status_app.run.InputFileWrapper.create")
@patch("gather_submission_status_app.run.GearBotClient.create")
def test_reload_workers_one_accepted(mock_bot_create, mock_input_create, mock_context):
    """Test that reload_workers=1 is accepted (valid minimum)."""
    mock_bot_create.return_value = Mock()
    mock_input_create.return_value = Mock()
    mock_context.config.opts["reload_workers"] = 1

    visitor = GatherSubmissionStatusVisitor.create(mock_context)
    assert visitor is not None
