"""Unit tests for run.py client creation in ProjectCreationVisitor.

Tests the behavior of ProjectCreationVisitor.run() with respect to
authorization client creation and error handling.

Validates: Requirements 11.1, 11.2
"""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from authorization import ConfigurationError
from authorization.client import AuthorizationClient
from fw_gear import GearContext
from gear_execution.gear_execution import ClientWrapper
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
def empty_project_file(tmp_path: Path) -> Path:
    """Create a minimal YAML project file that produces an empty study list.

    Uses a single empty YAML document so load_all_from_stream returns [None],
    then patches StudyModel.create to return a mock so no real parsing occurs.
    """
    project_file = tmp_path / "empty-project.yaml"
    project_file.write_text("---\n{}\n")
    return project_file


@pytest.fixture
def visitor(mock_client_wrapper: MagicMock, empty_project_file: Path) -> ProjectCreationVisitor:
    """Create a ProjectCreationVisitor with mocked dependencies."""
    return ProjectCreationVisitor(
        admin_id="nacc",
        client=mock_client_wrapper,
        project_filepath=empty_project_file,
    )


class TestRunClientCreationSuccess:
    """Tests for successful client creation in run().

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
        visitor: ProjectCreationVisitor,
        mock_gear_context: MagicMock,
    ) -> None:
        """Successful client creation passes the client to main.run()."""
        mock_auth_client = MagicMock(spec=AuthorizationClient)
        mock_create_client.return_value = mock_auth_client

        visitor.run(mock_gear_context)

        mock_main_run.assert_called_once()
        call_kwargs = mock_main_run.call_args[1]
        assert call_kwargs["authorization_client"] is mock_auth_client


class TestRunClientCreationConfigurationError:
    """Tests for ConfigurationError during client creation.

    Validates: Requirement 11.2
    """

    @patch("project_app.run.run")
    @patch("project_app.run.create_authorization_client")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_configuration_error_results_in_none_client(
        self,
        mock_study_create: MagicMock,
        mock_create_client: MagicMock,
        mock_main_run: MagicMock,
        visitor: ProjectCreationVisitor,
        mock_gear_context: MagicMock,
    ) -> None:
        """ConfigurationError results in None authorization_client."""
        mock_create_client.side_effect = ConfigurationError(
            "Missing AUTHORIZATION_API_URL"
        )

        visitor.run(mock_gear_context)

        mock_main_run.assert_called_once()
        call_kwargs = mock_main_run.call_args[1]
        assert call_kwargs["authorization_client"] is None

    @patch("project_app.run.run")
    @patch("project_app.run.create_authorization_client")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_configuration_error_logs_error(
        self,
        mock_study_create: MagicMock,
        mock_create_client: MagicMock,
        mock_main_run: MagicMock,
        visitor: ProjectCreationVisitor,
        mock_gear_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """ConfigurationError logs an error with the failure reason."""
        mock_create_client.side_effect = ConfigurationError(
            "Missing AUTHORIZATION_API_URL"
        )

        with caplog.at_level(logging.ERROR):
            visitor.run(mock_gear_context)

        assert any(
            "Authorization client creation failed" in record.message
            and "Missing AUTHORIZATION_API_URL" in record.message
            for record in caplog.records
        )


class TestRunClientCreationMissingConfig:
    """Tests for missing configuration (no env var, no explicit URL).

    When create_authorization_client raises ConfigurationError due to
    missing config, the gear treats it the same as any ConfigurationError:
    logs error and passes None to main.run().

    Validates: Requirement 11.2
    """

    @patch("project_app.run.run")
    @patch("project_app.run.create_authorization_client")
    @patch("project_app.run.StudyModel.create", return_value=MagicMock())
    def test_missing_config_results_in_none_client_and_error_log(
        self,
        mock_study_create: MagicMock,
        mock_create_client: MagicMock,
        mock_main_run: MagicMock,
        visitor: ProjectCreationVisitor,
        mock_gear_context: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Missing config raises ConfigurationError, resulting in None client
        and error log."""
        mock_create_client.side_effect = ConfigurationError(
            "No base URL configured: AUTHORIZATION_API_URL not set"
        )

        with caplog.at_level(logging.ERROR):
            visitor.run(mock_gear_context)

        # Client should be None
        mock_main_run.assert_called_once()
        call_kwargs = mock_main_run.call_args[1]
        assert call_kwargs["authorization_client"] is None

        # Error should be logged
        assert any(
            "Authorization client creation failed" in record.message
            and "hierarchy seeding disabled" in record.message
            for record in caplog.records
        )
