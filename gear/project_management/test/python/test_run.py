"""Unit tests for run.py client creation in ProjectCreationVisitor.

Tests the behavior of ProjectCreationVisitor.run() with respect to
authorization client creation via SSM parameter store.

Validates: Requirements 11.1, 11.2
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from authorization.client import AuthorizationClient
from fw_gear import GearContext
from gear_execution.gear_execution import ClientWrapper
from inputs.parameter_store import ParameterError, ParameterStore
from project_app.run import ProjectCreationVisitor


@pytest.fixture
def mock_client_wrapper() -> MagicMock:
    """Create a mock ClientWrapper."""
    wrapper = MagicMock(spec=ClientWrapper)
    wrapper.get_proxy.return_value = MagicMock()
    return wrapper


@pytest.fixture
def mock_gear_context() -> MagicMock:
    """Create a mock GearContext."""
    return MagicMock(spec=GearContext)


@pytest.fixture
def mock_parameter_store() -> MagicMock:
    """Create a mock ParameterStore."""
    return MagicMock(spec=ParameterStore)


@pytest.fixture
def empty_project_file(tmp_path: Path) -> Path:
    """Create a minimal YAML project file."""
    project_file = tmp_path / "empty-project.yaml"
    project_file.write_text("---\n{}\n")
    return project_file


class TestRunClientCreationSuccess:
    """Tests for successful client creation from SSM parameter store.

    Validates: Requirement 11.1
    """

    @patch("project_app.run.run")
    @patch("project_app.run.create_authorization_client")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_successful_client_creation_passes_client_to_main_run(
        self,
        mock_study_create: MagicMock,
        mock_create_client: MagicMock,
        mock_main_run: MagicMock,
        mock_client_wrapper: MagicMock,
        mock_parameter_store: MagicMock,
        empty_project_file: Path,
        mock_gear_context: MagicMock,
    ) -> None:
        """Successful SSM lookup and client creation passes client to run()."""
        mock_parameter_store.get_url.return_value = {
            "url": "https://api.example.com/auth"
        }
        mock_auth_client = MagicMock(spec=AuthorizationClient)
        mock_create_client.return_value = mock_auth_client

        visitor = ProjectCreationVisitor(
            admin_id="nacc",
            client=mock_client_wrapper,
            project_filepath=empty_project_file,
            parameter_store=mock_parameter_store,
            authorization_path="/prod/authorization/api-endpoint",
        )

        visitor.run(mock_gear_context)

        mock_parameter_store.get_url.assert_called_once_with(
            "/prod/authorization/api-endpoint"
        )
        mock_create_client.assert_called_once_with(
            base_url="https://api.example.com/auth"
        )
        mock_main_run.assert_called_once()
        call_kwargs = mock_main_run.call_args[1]
        assert call_kwargs["authorization_client"] is mock_auth_client


class TestRunClientCreationParameterError:
    """Tests for ParameterError during SSM lookup.

    Validates: Requirement 11.2
    """

    @patch("project_app.run.run")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_parameter_error_results_in_none_client(
        self,
        mock_study_create: MagicMock,
        mock_main_run: MagicMock,
        mock_client_wrapper: MagicMock,
        mock_parameter_store: MagicMock,
        empty_project_file: Path,
        mock_gear_context: MagicMock,
    ) -> None:
        """ParameterError from SSM results in None authorization_client."""
        mock_parameter_store.get_url.side_effect = ParameterError("Parameter not found")

        visitor = ProjectCreationVisitor(
            admin_id="nacc",
            client=mock_client_wrapper,
            project_filepath=empty_project_file,
            parameter_store=mock_parameter_store,
            authorization_path="/prod/authorization/api-endpoint",
        )

        visitor.run(mock_gear_context)

        mock_main_run.assert_called_once()
        call_kwargs = mock_main_run.call_args[1]
        assert call_kwargs["authorization_client"] is None

    @patch("project_app.run.run")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_parameter_error_logs_error(
        self,
        mock_study_create: MagicMock,
        mock_main_run: MagicMock,
        mock_client_wrapper: MagicMock,
        mock_parameter_store: MagicMock,
        empty_project_file: Path,
        mock_gear_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ParameterError logs an error message."""
        mock_parameter_store.get_url.side_effect = ParameterError("Parameter not found")

        visitor = ProjectCreationVisitor(
            admin_id="nacc",
            client=mock_client_wrapper,
            project_filepath=empty_project_file,
            parameter_store=mock_parameter_store,
            authorization_path="/prod/authorization/api-endpoint",
        )

        with caplog.at_level(logging.ERROR):
            visitor.run(mock_gear_context)

        assert any(
            "Authorization client creation failed" in record.message
            for record in caplog.records
        )


class TestRunClientCreationNoConfig:
    """Tests for when no parameter store or path is configured.

    Validates: Requirement 11.2
    """

    @patch("project_app.run.run")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_no_path_results_in_none_client_and_warning(
        self,
        mock_study_create: MagicMock,
        mock_main_run: MagicMock,
        mock_client_wrapper: MagicMock,
        empty_project_file: Path,
        mock_gear_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """No authorization_path results in None client and warning log."""
        visitor = ProjectCreationVisitor(
            admin_id="nacc",
            client=mock_client_wrapper,
            project_filepath=empty_project_file,
            parameter_store=None,
            authorization_path=None,
        )

        with caplog.at_level(logging.WARNING):
            visitor.run(mock_gear_context)

        mock_main_run.assert_called_once()
        call_kwargs = mock_main_run.call_args[1]
        assert call_kwargs["authorization_client"] is None

        assert any(
            "hierarchy seeding is disabled" in record.message
            for record in caplog.records
        )
