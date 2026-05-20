"""Unit tests for main.py with optional AuthorizationClient.

Tests the run() function behavior when authorization_client is None,
when a valid client is provided, and when failures occur during seeding.

Validates: Requirements 11.1, 11.3, 7.3
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from authorization.client import AuthorizationClient
from centers.nacc_group import NACCGroup
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from project_app.main import run
from projects.study import StudyModel


@pytest.fixture
def mock_proxy() -> MagicMock:
    """Create a mock FlywheelProxy."""
    return MagicMock(spec=FlywheelProxy)


@pytest.fixture
def mock_admin_group() -> MagicMock:
    """Create a mock NACCGroup with default user access."""
    group = MagicMock(spec=NACCGroup)
    group.get_user_access.return_value = []
    return group


@pytest.fixture
def mock_authorization_client() -> MagicMock:
    """Create a mock AuthorizationClient."""
    return MagicMock(spec=AuthorizationClient)


@pytest.fixture
def empty_study_list() -> list[StudyModel]:
    """Return an empty study list for tests that don't need studies."""
    return []


class TestRunWithNoClient:
    """Tests for run() when authorization_client is None.

    Validates: Requirement 11.1
    """

    def test_logs_warning_when_client_is_none(
        self,
        mock_proxy: MagicMock,
        mock_admin_group: MagicMock,
        empty_study_list: list[StudyModel],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """run() with authorization_client=None logs a warning."""
        with caplog.at_level(logging.WARNING):
            run(
                proxy=mock_proxy,
                admin_group=mock_admin_group,
                study_list=empty_study_list,
                authorization_client=None,
            )

        assert any(
            "Authorization hierarchy seeding is disabled" in record.message
            for record in caplog.records
        )

    @patch("project_app.main.ResourceHierarchySeeder")
    def test_does_not_create_seeder_when_client_is_none(
        self,
        mock_seeder_class: MagicMock,
        mock_proxy: MagicMock,
        mock_admin_group: MagicMock,
        empty_study_list: list[StudyModel],
    ) -> None:
        """run() with authorization_client=None does not instantiate seeder."""
        run(
            proxy=mock_proxy,
            admin_group=mock_admin_group,
            study_list=empty_study_list,
            authorization_client=None,
        )

        mock_seeder_class.assert_not_called()


class TestRunWithValidClient:
    """Tests for run() when a valid AuthorizationClient is provided.

    Validates: Requirement 11.3
    """

    @patch("project_app.main.StudyMappingVisitor")
    @patch("project_app.main.ResourceHierarchySeeder")
    def test_creates_seeder_with_client(
        self,
        mock_seeder_class: MagicMock,
        mock_visitor_class: MagicMock,
        mock_proxy: MagicMock,
        mock_admin_group: MagicMock,
        mock_authorization_client: MagicMock,
        empty_study_list: list[StudyModel],
    ) -> None:
        """run() with a valid client creates ResourceHierarchySeeder."""
        mock_seeder_instance = MagicMock()
        mock_seeder_instance.failure_count = 0
        mock_seeder_class.return_value = mock_seeder_instance

        run(
            proxy=mock_proxy,
            admin_group=mock_admin_group,
            study_list=empty_study_list,
            authorization_client=mock_authorization_client,
        )

        mock_seeder_class.assert_called_once_with(client=mock_authorization_client)

    @patch("project_app.main.StudyMappingVisitor")
    @patch("project_app.main.ResourceHierarchySeeder")
    def test_passes_seeder_to_visitor(
        self,
        mock_seeder_class: MagicMock,
        mock_visitor_class: MagicMock,
        mock_proxy: MagicMock,
        mock_admin_group: MagicMock,
        mock_authorization_client: MagicMock,
        empty_study_list: list[StudyModel],
    ) -> None:
        """run() passes the seeder instance to StudyMappingVisitor."""
        mock_seeder_instance = MagicMock()
        mock_seeder_instance.failure_count = 0
        mock_seeder_class.return_value = mock_seeder_instance

        run(
            proxy=mock_proxy,
            admin_group=mock_admin_group,
            study_list=empty_study_list,
            authorization_client=mock_authorization_client,
        )

        mock_visitor_class.assert_called_once_with(
            flywheel_proxy=mock_proxy,
            admin_permissions=mock_admin_group.get_user_access(),
            hierarchy_seeder=mock_seeder_instance,
        )


class TestRunFailureCountWarning:
    """Tests for failure count warning logging.

    Validates: Requirement 7.3
    """

    @patch("project_app.main.StudyMappingVisitor")
    @patch("project_app.main.ResourceHierarchySeeder")
    def test_logs_warning_when_failures_occur(
        self,
        mock_seeder_class: MagicMock,
        mock_visitor_class: MagicMock,
        mock_proxy: MagicMock,
        mock_admin_group: MagicMock,
        mock_authorization_client: MagicMock,
        empty_study_list: list[StudyModel],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """run() logs a warning when seeder has failures."""
        mock_seeder_instance = MagicMock()
        mock_seeder_instance.failure_count = 3
        mock_seeder_class.return_value = mock_seeder_instance

        with caplog.at_level(logging.WARNING):
            run(
                proxy=mock_proxy,
                admin_group=mock_admin_group,
                study_list=empty_study_list,
                authorization_client=mock_authorization_client,
            )

        assert any("3 failure(s)" in record.message for record in caplog.records)

    @patch("project_app.main.StudyMappingVisitor")
    @patch("project_app.main.ResourceHierarchySeeder")
    def test_no_warning_when_no_failures(
        self,
        mock_seeder_class: MagicMock,
        mock_visitor_class: MagicMock,
        mock_proxy: MagicMock,
        mock_admin_group: MagicMock,
        mock_authorization_client: MagicMock,
        empty_study_list: list[StudyModel],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """run() does not log failure warning when failure_count is 0."""
        mock_seeder_instance = MagicMock()
        mock_seeder_instance.failure_count = 0
        mock_seeder_class.return_value = mock_seeder_instance

        with caplog.at_level(logging.WARNING):
            run(
                proxy=mock_proxy,
                admin_group=mock_admin_group,
                study_list=empty_study_list,
                authorization_client=mock_authorization_client,
            )

        assert not any("failure(s)" in record.message for record in caplog.records)
