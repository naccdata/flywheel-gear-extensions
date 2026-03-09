"""Unit tests for GeneralAuthorizationVisitor."""

from unittest.mock import Mock

import pytest
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import ProjectError
from users.authorization_visitor import GeneralAuthorizationVisitor
from users.authorizations import (
    AuthMap,
    Authorizations,
    PageResource,
)
from users.event_models import EventCategory, EventType, UserEventCollector


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
def mock_nacc_group():
    """Create a mock NACC group."""
    group = Mock()
    group.id = "nacc"
    return group


@pytest.fixture
def mock_auth_map():
    """Create a mock authorization map."""
    return Mock(spec=AuthMap)


@pytest.fixture
def mock_collector():
    """Create a mock event collector."""
    return Mock(spec=UserEventCollector)


@pytest.fixture
def page_resource():
    """Create a page resource for testing."""
    return PageResource(page="web")


@pytest.fixture
def authorizations_with_page():
    """Create authorizations with a page resource activity."""
    authorizations = Authorizations()
    page_resource = PageResource(page="web")
    authorizations.add(resource=page_resource, action="view")
    return authorizations


class TestGeneralAuthorizationVisitorConstructor:
    """Tests for GeneralAuthorizationVisitor constructor."""

    def test_constructor_stores_all_parameters(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
    ):
        """Test that constructor accepts and stores all required parameters."""
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )

        # Verify visitor was created successfully
        assert visitor is not None


class TestVisitPageResourceSuccess:
    """Tests for successful page resource processing."""

    def test_visit_page_resource_with_valid_project_assigns_roles(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that visit_page_resource assigns roles when project exists."""
        # Setup mocks
        mock_project = Mock()
        mock_nacc_group.get_project.return_value = mock_project

        mock_role = Mock()
        mock_role.label = "read-only"
        mock_auth_map.get.return_value = [mock_role]

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify project was retrieved with correct label
        mock_nacc_group.get_project.assert_called_once_with("page-web")

        # Verify auth_map was queried
        assert mock_auth_map.get.called

        # Verify roles were assigned
        mock_project.add_user_roles.assert_called_once_with(
            user=mock_user, roles=[mock_role]
        )

        # Verify no error events were collected
        mock_collector.collect.assert_not_called()

    def test_project_label_construction_format(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
    ):
        """Test that project label is constructed as 'page-{page_name}'."""
        # Setup mocks
        mock_project = Mock()
        mock_nacc_group.get_project.return_value = mock_project
        mock_auth_map.get.return_value = [Mock()]

        # Create visitor
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )

        # Test with different page names
        test_cases = [
            ("web", "page-web"),
            ("presentations", "page-presentations"),
            ("webinars", "page-webinars"),
        ]

        for page_name, expected_label in test_cases:
            mock_nacc_group.get_project.reset_mock()
            page_res = PageResource(page=page_name)
            visitor.visit_page_resource(page_res)
            mock_nacc_group.get_project.assert_called_once_with(expected_label)


class TestVisitPageResourceMissingProject:
    """Tests for handling missing page projects."""

    def test_missing_project_collects_error_event_with_flywheel_error_category(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that missing project collects error event with
        FLYWHEEL_ERROR."""
        # Setup: project not found
        mock_nacc_group.get_project.return_value = None

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify error event was collected
        mock_collector.collect.assert_called_once()
        error_event = mock_collector.collect.call_args[0][0]

        # Verify error event properties
        assert error_event.event_type == EventType.ERROR.value
        assert error_event.category == EventCategory.FLYWHEEL_ERROR.value
        assert error_event.user_context.email == "test@example.com"
        assert error_event.user_context.registry_id == "test-user-id"
        assert "Page project not found" in error_event.message
        assert "page-web" in error_event.message
        assert (
            error_event.action_needed
            == "create_page_project_or_update_authorization_config"
        )

    def test_missing_project_returns_early_without_assigning_roles(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that missing project returns early without role assignment."""
        # Setup: project not found
        mock_nacc_group.get_project.return_value = None

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify auth_map was not queried
        mock_auth_map.get.assert_not_called()


class TestVisitPageResourceMissingRoles:
    """Tests for handling missing authorization map entries."""

    def test_missing_roles_collects_error_event_with_insufficient_permissions(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that missing roles collects error with
        INSUFFICIENT_PERMISSIONS."""
        # Setup: project exists but no roles found
        mock_project = Mock()
        mock_nacc_group.get_project.return_value = mock_project
        mock_auth_map.get.return_value = []  # No roles

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify error event was collected
        mock_collector.collect.assert_called_once()
        error_event = mock_collector.collect.call_args[0][0]

        # Verify error event properties
        assert error_event.event_type == EventType.ERROR.value
        assert error_event.category == EventCategory.INSUFFICIENT_PERMISSIONS.value
        assert error_event.user_context.email == "test@example.com"
        assert "No roles found" in error_event.message
        assert "test-user-id" in error_event.message
        assert "page-web" in error_event.message
        assert error_event.action_needed == "update_authorization_map_for_page_project"

    def test_missing_roles_returns_early_without_assigning_roles(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that missing roles returns early without role assignment."""
        # Setup: project exists but no roles found
        mock_project = Mock()
        mock_nacc_group.get_project.return_value = mock_project
        mock_auth_map.get.return_value = []

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify roles were not assigned
        mock_project.add_user_roles.assert_not_called()


class TestVisitPageResourceRoleAssignmentFailure:
    """Tests for handling role assignment failures."""

    def test_role_assignment_failure_collects_error_event_with_flywheel_error(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that role assignment failure collects error with
        FLYWHEEL_ERROR."""
        # Setup: project exists, roles found, but assignment fails
        mock_project = Mock()
        mock_nacc_group.get_project.return_value = mock_project
        mock_role = Mock()
        mock_auth_map.get.return_value = [mock_role]
        mock_project.add_user_roles.side_effect = ProjectError("Permission denied")

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify error event was collected
        mock_collector.collect.assert_called_once()
        error_event = mock_collector.collect.call_args[0][0]

        # Verify error event properties
        assert error_event.event_type == EventType.ERROR.value
        assert error_event.category == EventCategory.FLYWHEEL_ERROR.value
        assert error_event.user_context.email == "test@example.com"
        assert "Failed to assign roles" in error_event.message
        assert "page-web" in error_event.message
        assert "Permission denied" in error_event.message
        assert (
            error_event.action_needed == "check_flywheel_permissions_and_project_state"
        )

    def test_role_assignment_failure_does_not_raise_exception(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that role assignment failure doesn't raise exception."""
        # Setup: project exists, roles found, but assignment fails
        mock_project = Mock()
        mock_nacc_group.get_project.return_value = mock_project
        mock_role = Mock()
        mock_auth_map.get.return_value = [mock_role]
        mock_project.add_user_roles.side_effect = ProjectError("Permission denied")

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )

        # Should not raise exception
        visitor.visit_page_resource(page_resource)


class TestErrorEventContent:
    """Tests for error event content completeness."""

    def test_error_event_includes_user_context(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that error events include complete user context."""
        # Setup: missing project to trigger error
        mock_nacc_group.get_project.return_value = None

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Get the collected error event
        error_event = mock_collector.collect.call_args[0][0]

        # Verify user context is complete
        assert error_event.user_context.email == "test@example.com"
        assert error_event.user_context.name == "Test User"
        assert error_event.user_context.registry_id == "test-user-id"

    def test_error_event_includes_descriptive_message(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that error events include descriptive messages."""
        # Setup: missing project to trigger error
        mock_nacc_group.get_project.return_value = None

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Get the collected error event
        error_event = mock_collector.collect.call_args[0][0]

        # Verify message is descriptive
        assert error_event.message is not None
        assert len(error_event.message) > 0
        assert "page-web" in error_event.message

    def test_error_event_includes_action_needed(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that error events include action_needed field."""
        # Setup: missing project to trigger error
        mock_nacc_group.get_project.return_value = None

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Get the collected error event
        error_event = mock_collector.collect.call_args[0][0]

        # Verify action_needed is present
        assert error_event.action_needed is not None
        assert len(error_event.action_needed) > 0

    def test_collector_collect_is_called_for_each_error(
        self,
        mock_user,
        authorizations_with_page,
        mock_auth_map,
        mock_nacc_group,
        mock_collector,
        page_resource,
    ):
        """Test that collector.collect() is called for each error event."""
        # Setup: missing project to trigger error
        mock_nacc_group.get_project.return_value = None

        # Create visitor and process page resource
        visitor = GeneralAuthorizationVisitor(
            user=mock_user,
            authorizations=authorizations_with_page,
            auth_map=mock_auth_map,
            nacc_group=mock_nacc_group,
            collector=mock_collector,
        )
        visitor.visit_page_resource(page_resource)

        # Verify collector.collect was called exactly once
        assert mock_collector.collect.call_count == 1
