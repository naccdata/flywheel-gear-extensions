"""Unit tests for UpdateUserProcess.__authorize_user() method.

Tests the general authorization functionality through the public visit()
method to avoid testing private implementation details.
"""

from unittest.mock import Mock, patch

import pytest
from flywheel.models.user import User
from users.authorization_visitor import GeneralAuthorizationVisitor
from users.authorizations import Authorizations, PageResource
from users.event_models import UserEventCollector
from users.user_entry import ActiveUserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_processes import UpdateUserProcess
from users.user_registry import RegistryPerson


@pytest.fixture
def mock_user():
    """Create a mock Flywheel user."""
    user = Mock(spec=User)
    user.id = "test-user-id"
    user.email = "test@example.com"
    user.firstname = "Test"
    user.lastname = "User"
    return user


@pytest.fixture
def mock_environment():
    """Create a mock user process environment."""
    env = Mock(spec=UserProcessEnvironment)
    env.admin_group = Mock()
    env.admin_group.id = "nacc"
    env.authorization_map = Mock()
    env.find_user = Mock()
    env.proxy = Mock()
    env.proxy.set_user_email = Mock()
    return env


@pytest.fixture
def mock_collector():
    """Create a mock event collector."""
    return Mock(spec=UserEventCollector)


@pytest.fixture
def update_user_process(mock_environment, mock_collector):
    """Create an UpdateUserProcess instance for testing."""
    return UpdateUserProcess(environment=mock_environment, collector=mock_collector)


@pytest.fixture
def empty_authorizations():
    """Create empty authorizations."""
    return Authorizations()


@pytest.fixture
def authorizations_with_page():
    """Create authorizations with a page resource activity."""
    authorizations = Authorizations()
    page_resource = PageResource(page="web")
    authorizations.add(resource=page_resource, action="view")
    return authorizations


@pytest.fixture
def authorizations_with_multiple_pages():
    """Create authorizations with multiple page resource activities."""
    authorizations = Authorizations()
    page_resource1 = PageResource(page="web")
    page_resource2 = PageResource(page="presentations")
    authorizations.add(resource=page_resource1, action="view")
    authorizations.add(resource=page_resource2, action="view")
    return authorizations


@pytest.fixture
def active_user_entry(empty_authorizations):
    """Create an active user entry for testing."""
    entry = Mock(spec=ActiveUserEntry)
    entry.email = "test@example.com"
    entry.registry_id = "test-user-id"
    entry.registry_person = Mock(spec=RegistryPerson)
    entry.authorizations = empty_authorizations
    entry.set_fw_user = Mock()
    return entry


class TestAuthorizeUserEmptyAuthorizations:
    """Tests for __authorize_user() with empty authorizations."""

    def test_empty_authorizations_logs_info_and_returns_early(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        mock_environment,
        caplog,
    ):
        """Test that empty authorizations logs info message and returns
        early."""
        # Setup
        import logging

        caplog.set_level(logging.INFO)
        active_user_entry.authorizations = Authorizations()
        mock_environment.find_user.return_value = mock_user

        # Call visit which internally calls __authorize_user
        update_user_process.visit(active_user_entry)

        # Verify info log message
        assert "No general authorizations for user test-user-id" in caplog.text

    def test_empty_authorizations_does_not_create_visitor(
        self, update_user_process, mock_user, active_user_entry, mock_environment
    ):
        """Test that empty authorizations does not create visitor."""
        # Setup
        active_user_entry.authorizations = Authorizations()
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            # Call visit which internally calls __authorize_user
            update_user_process.visit(active_user_entry)

            # Verify visitor was not created
            mock_visitor_class.assert_not_called()


class TestAuthorizeUserWithPageResources:
    """Tests for __authorize_user() with page resource authorizations."""

    def test_with_page_resource_creates_visitor(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_page,
        mock_environment,
    ):
        """Test that page resource authorizations create visitor."""
        # Setup
        active_user_entry.authorizations = authorizations_with_page
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            mock_visitor = Mock(spec=GeneralAuthorizationVisitor)
            mock_visitor_class.return_value = mock_visitor

            # Call visit which internally calls __authorize_user
            update_user_process.visit(active_user_entry)

            # Verify visitor was created with correct parameters
            mock_visitor_class.assert_called_once_with(
                user=mock_user,
                authorizations=authorizations_with_page,
                auth_map=mock_environment.authorization_map,
                nacc_group=mock_environment.admin_group,
                collector=update_user_process.collector,
            )

    def test_with_page_resource_processes_activity(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_page,
        mock_environment,
    ):
        """Test that page resource activity is processed."""
        # Setup
        active_user_entry.authorizations = authorizations_with_page
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            mock_visitor = Mock(spec=GeneralAuthorizationVisitor)
            mock_visitor_class.return_value = mock_visitor

            # Call visit which internally calls __authorize_user
            update_user_process.visit(active_user_entry)

            # Verify visit_page_resource was called
            assert mock_visitor.visit_page_resource.call_count == 1
            # Verify it was called with a PageResource
            call_args = mock_visitor.visit_page_resource.call_args
            assert isinstance(call_args[0][0], PageResource)

    def test_with_multiple_page_resources_processes_all(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_multiple_pages,
        mock_environment,
    ):
        """Test that multiple page resource activities are all processed."""
        # Setup
        active_user_entry.authorizations = authorizations_with_multiple_pages
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            mock_visitor = Mock(spec=GeneralAuthorizationVisitor)
            mock_visitor_class.return_value = mock_visitor

            # Call visit which internally calls __authorize_user
            update_user_process.visit(active_user_entry)

            # Verify visit_page_resource was called twice
            assert mock_visitor.visit_page_resource.call_count == 2


class TestAuthorizeUserAdminGroupAccess:
    """Tests for admin_group property access."""

    def test_accesses_admin_group_from_environment(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_page,
        mock_environment,
    ):
        """Test that admin_group is accessed from environment."""
        # Setup
        active_user_entry.authorizations = authorizations_with_page
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            mock_visitor = Mock(spec=GeneralAuthorizationVisitor)
            mock_visitor_class.return_value = mock_visitor

            # Call visit which internally calls __authorize_user
            update_user_process.visit(active_user_entry)

            # Verify admin_group was accessed
            # This is verified indirectly through the visitor creation call
            mock_visitor_class.assert_called_once()
            call_kwargs = mock_visitor_class.call_args[1]
            assert call_kwargs["nacc_group"] == mock_environment.admin_group


class TestAuthorizeUserErrorHandling:
    """Tests for error handling in __authorize_user()."""

    def test_unexpected_exception_is_caught_and_logged(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_page,
        mock_environment,
        caplog,
    ):
        """Test that unexpected exceptions are caught and logged."""
        # Setup
        active_user_entry.authorizations = authorizations_with_page
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            # Make visitor creation raise an exception
            mock_visitor_class.side_effect = RuntimeError("Unexpected error")

            # Call visit - should not raise
            update_user_process.visit(active_user_entry)

            # Verify error was logged
            assert "Unexpected error during general authorization" in caplog.text
            assert "test-user-id" in caplog.text

    def test_exception_does_not_propagate(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_page,
        mock_environment,
    ):
        """Test that exceptions do not propagate from __authorize_user()."""
        # Setup
        active_user_entry.authorizations = authorizations_with_page
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            # Make visitor creation raise an exception
            mock_visitor_class.side_effect = RuntimeError("Unexpected error")

            # Call visit - should not raise
            try:
                update_user_process.visit(active_user_entry)
            except Exception as e:
                pytest.fail(f"Exception should not propagate: {e}")

    def test_visitor_exception_is_caught_and_logged(
        self,
        update_user_process,
        mock_user,
        active_user_entry,
        authorizations_with_page,
        mock_environment,
        caplog,
    ):
        """Test that exceptions from visitor are caught and logged."""
        # Setup
        active_user_entry.authorizations = authorizations_with_page
        mock_environment.find_user.return_value = mock_user

        with patch(
            "users.user_processes.GeneralAuthorizationVisitor"
        ) as mock_visitor_class:
            mock_visitor = Mock(spec=GeneralAuthorizationVisitor)
            mock_visitor.visit_page_resource.side_effect = RuntimeError("Visitor error")
            mock_visitor_class.return_value = mock_visitor

            # Call visit - should not raise
            update_user_process.visit(active_user_entry)

            # Verify error was logged
            assert "Unexpected error during general authorization" in caplog.text
