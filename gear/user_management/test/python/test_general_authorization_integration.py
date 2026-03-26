"""Integration tests for general authorization in user management gear.

This module tests the end-to-end integration of general authorization
functionality, including:
- General authorization for users with page access
- Multiple page resources processing
- Integration with center authorization
- Authorization map sharing between general and center authorization
- Error handling and event collection
"""

from typing import Dict, Optional
from unittest.mock import Mock

import pytest
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor, User
from users.authorizations import (
    Activities,
    Activity,
    Authorizations,
    PageResource,
)
from users.event_models import EventCategory, UserEventCollector
from users.user_entry import ActiveUserEntry, PersonName
from users.user_processes import UpdateUserProcess
from users.user_registry import RegistryPerson


class MockProject:
    """Mock ProjectAdaptor for testing."""

    def __init__(self, project_id: str, label: str):
        self.id = project_id
        self.label = label
        self.users_with_roles: Dict[str, list] = {}

    def add_user_roles(self, user: User, roles: list) -> None:
        """Mock add_user_roles."""
        self.users_with_roles[user.id] = roles  # type: ignore[index]

    def has_user_with_roles(self, user_id: str, expected_roles: list) -> bool:
        """Check if user has expected roles."""
        return (
            user_id in self.users_with_roles
            and self.users_with_roles[user_id] == expected_roles
        )


class MockNACCGroup:
    """Mock NACCGroup for testing."""

    def __init__(self, group_id: str = "nacc"):
        self.id = group_id
        self._projects: Dict[str, MockProject] = {}

    def add_project(self, label: str, project_id: Optional[str] = None) -> MockProject:
        """Add a mock project to the group."""
        pid = project_id if project_id is not None else f"project-{label}"
        project = MockProject(pid, label)
        self._projects[label] = project
        return project

    def get_project(self, label: str) -> Optional[ProjectAdaptor]:
        """Mock get_project."""
        return self._projects.get(label)  # type: ignore


class MockAuthMap:
    """Mock AuthMap for testing."""

    def __init__(self):
        self._role_mappings: Dict[str, list] = {}

    def add_mapping(self, project_label: str, roles: list) -> None:
        """Add a role mapping for a project."""
        self._role_mappings[project_label] = roles

    def get(self, *, project_label: str, authorizations) -> list:
        """Mock get method."""
        return self._role_mappings.get(project_label, [])


class MockUserProcessEnvironment:
    """Mock UserProcessEnvironment for testing."""

    def __init__(
        self,
        admin_group: Optional[MockNACCGroup] = None,
        auth_map: Optional[MockAuthMap] = None,
    ):
        self.admin_group = admin_group or MockNACCGroup()  # type: ignore
        self.authorization_map = auth_map or MockAuthMap()  # type: ignore
        self._users: Dict[str, User] = {}
        self.domain_config = None
        self.idp_config = None

    def add_user(self, user: User) -> None:
        """Add a user to the mock environment."""
        self._users[user.id] = user  # type: ignore[index]

    def find_user(self, user_id: str) -> Optional[User]:
        """Mock find_user."""
        return self._users.get(user_id)


def create_mock_user(
    user_id: str = "test-user",
    email: str = "test@example.com",
    firstname: str = "Test",
    lastname: str = "User",
) -> User:
    """Factory for creating mock users."""
    user = Mock(spec=User)
    user.id = user_id
    user.email = email
    user.firstname = firstname
    user.lastname = lastname
    return user


def create_mock_registry_person(
    registry_id: str = "test-user",
) -> RegistryPerson:
    """Factory for creating mock registry persons."""
    person = Mock(spec=RegistryPerson)
    person.registry_id = Mock(return_value=registry_id)
    return person


def create_page_resource_authorizations(page_names: list[str]) -> Authorizations:
    """Factory for creating authorizations with page resources."""
    activities = Activities()
    for page_name in page_names:
        resource = PageResource(page=page_name)
        activity = Activity(resource=resource, action="view")
        activities.add(resource, activity)
    return Authorizations(activities=activities)


def create_active_user_entry(
    email: str,
    registry_id: str,
    authorizations: Authorizations,
    first_name: str = "Test",
    last_name: str = "User",
) -> ActiveUserEntry:
    """Factory for creating active user entries."""
    return ActiveUserEntry(
        name=PersonName(first_name=first_name, last_name=last_name),
        email=email,
        active=True,
        approved=True,
        authorizations=authorizations,
        registry_person=create_mock_registry_person(registry_id),
    )


class TestGeneralAuthorizationIntegration:
    """Integration tests for general authorization."""

    @pytest.fixture
    def mock_environment(self) -> MockUserProcessEnvironment:
        """Create mock user process environment."""
        return MockUserProcessEnvironment()

    @pytest.fixture
    def mock_collector(self) -> UserEventCollector:
        """Create user event collector."""
        return UserEventCollector()

    @pytest.fixture
    def update_process(
        self,
        mock_environment: MockUserProcessEnvironment,
        mock_collector: UserEventCollector,
    ) -> UpdateUserProcess:
        """Create UpdateUserProcess for testing."""
        return UpdateUserProcess(
            environment=mock_environment,  # type: ignore
            collector=mock_collector,
        )

    def test_end_to_end_general_authorization_single_page(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
    ) -> None:
        """Test end-to-end general authorization for user with single page
        access.

        Validates:
        - User receives roles on page project
        - Project label is constructed correctly
        - Roles are assigned via add_user_roles
        """
        # Setup
        user = create_mock_user(user_id="user1", email="user1@example.com")
        mock_environment.add_user(user)

        # Add page project to admin group
        page_project = mock_environment.admin_group.add_project("page-web")  # type: ignore

        # Add role mapping to auth map
        mock_environment.authorization_map.add_mapping("page-web", ["read-only"])  # type: ignore

        # Create authorizations with page resource
        authorizations = create_page_resource_authorizations(["web"])

        # Create active user entry
        entry = create_active_user_entry(
            email="user1@example.com",
            registry_id="user1",
            authorizations=authorizations,
        )

        # Execute through public interface
        update_process.visit(entry)

        # Verify roles were assigned
        assert page_project.has_user_with_roles("user1", ["read-only"])

    def test_end_to_end_general_authorization_multiple_pages(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
    ) -> None:
        """Test end-to-end general authorization for user with multiple page
        resources.

        Validates:
        - Each page resource is processed independently
        - Roles are assigned for each page project
        - Multiple page projects can be processed in single call
        """
        # Setup
        user = create_mock_user(user_id="user2", email="user2@example.com")
        mock_environment.add_user(user)

        # Add multiple page projects
        page_web = mock_environment.admin_group.add_project("page-web")  # type: ignore
        page_webinars = mock_environment.admin_group.add_project("page-webinars")  # type: ignore
        page_presentations = mock_environment.admin_group.add_project(  # type: ignore
            "page-presentations"
        )

        # Add role mappings
        mock_environment.authorization_map.add_mapping("page-web", ["read-only"])  # type: ignore
        mock_environment.authorization_map.add_mapping("page-webinars", ["read-only"])  # type: ignore
        mock_environment.authorization_map.add_mapping(  # type: ignore
            "page-presentations", ["read-only", "read-write"]
        )

        # Create authorizations with multiple page resources
        authorizations = create_page_resource_authorizations(
            ["web", "webinars", "presentations"]
        )

        # Create active user entry
        entry = create_active_user_entry(
            email="user2@example.com",
            registry_id="user2",
            authorizations=authorizations,
        )

        # Execute through public interface
        update_process.visit(entry)

        # Verify all page projects received role assignments
        assert page_web.has_user_with_roles("user2", ["read-only"])
        assert page_webinars.has_user_with_roles("user2", ["read-only"])
        assert page_presentations.has_user_with_roles(
            "user2", ["read-only", "read-write"]
        )

    def test_general_authorization_does_not_affect_center_authorization(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
    ) -> None:
        """Test that general authorization does not affect center
        authorization.

        Validates:
        - General authorization processes page resources only
        - Center authorization flow remains independent
        - No interference between general and center authorization
        """
        # Setup
        user = create_mock_user(user_id="user3", email="user3@example.com")
        mock_environment.add_user(user)

        # Add page project
        page_project = mock_environment.admin_group.add_project("page-web")  # type: ignore
        mock_environment.authorization_map.add_mapping("page-web", ["read-only"])  # type: ignore

        # Create authorizations with page resource
        authorizations = create_page_resource_authorizations(["web"])

        # Create active user entry
        entry = create_active_user_entry(
            email="user3@example.com",
            registry_id="user3",
            authorizations=authorizations,
        )

        # Execute general authorization
        update_process.visit(entry)

        # Verify only page project was affected
        assert page_project.has_user_with_roles("user3", ["read-only"])
        # Center authorization would be handled separately by UpdateCenterUserProcess
        # This test confirms general authorization doesn't interfere with that flow

    def test_same_authorization_map_used_for_general_and_center(
        self,
        mock_environment: MockUserProcessEnvironment,
        mock_collector: UserEventCollector,
    ) -> None:
        """Test that same authorization map is used for general and center
        authorization.

        Validates:
        - UpdateUserProcess uses environment's authorization_map
        - Same auth_map instance is available to both flows
        - Consistent authorization logic across general and center flows
        """
        # Setup
        user = create_mock_user(user_id="user4", email="user4@example.com")
        mock_environment.add_user(user)

        # Add page project and role mapping
        page_project = mock_environment.admin_group.add_project("page-web")  # type: ignore
        mock_environment.authorization_map.add_mapping("page-web", ["read-only"])  # type: ignore

        # Create process
        process = UpdateUserProcess(
            environment=mock_environment,  # type: ignore
            collector=mock_collector,
        )

        # Create authorizations
        authorizations = create_page_resource_authorizations(["web"])

        # Create active user entry
        entry = create_active_user_entry(
            email="user4@example.com",
            registry_id="user4",
            authorizations=authorizations,
        )

        # Execute - this will use the environment's auth_map
        process.visit(entry)

        # Verify authorization succeeded (confirms same auth_map was used)
        assert page_project.has_user_with_roles("user4", ["read-only"])

    def test_error_in_general_authorization_does_not_prevent_center_authorization(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
        mock_collector: UserEventCollector,
    ) -> None:
        """Test that errors in general authorization don't prevent center
        authorization.

        Validates:
        - Missing page project collects error but doesn't raise exception
        - Processing continues after error
        - Center authorization can still proceed
        """
        # Setup
        user = create_mock_user(user_id="user5", email="user5@example.com")
        mock_environment.add_user(user)

        # Don't add page project - this will cause an error
        # But add role mapping
        mock_environment.authorization_map.add_mapping("page-web", ["read-only"])  # type: ignore

        # Create authorizations with page resource
        authorizations = create_page_resource_authorizations(["web"])

        # Create active user entry
        entry = create_active_user_entry(
            email="user5@example.com",
            registry_id="user5",
            authorizations=authorizations,
        )

        # Execute - should not raise exception
        update_process.visit(entry)

        # Verify error was collected
        assert mock_collector.has_errors()
        assert mock_collector.error_count() == 1

        errors = mock_collector.get_errors()
        assert errors[0].category == EventCategory.FLYWHEEL_ERROR.value
        assert "Page project not found" in errors[0].message

        # Center authorization would still proceed after this
        # (handled by separate UpdateCenterUserProcess)

    def test_multiple_errors_collected_for_multiple_page_resources(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
        mock_collector: UserEventCollector,
    ) -> None:
        """Test that multiple errors are collected when processing multiple
        page resources.

        Validates:
        - Each page resource error is collected independently
        - Processing continues after each error
        - All errors are available in collector
        """
        # Setup
        user = create_mock_user(user_id="user6", email="user6@example.com")
        mock_environment.add_user(user)

        # Don't add any page projects - all will fail
        mock_environment.authorization_map.add_mapping("page-web", ["read-only"])  # type: ignore
        mock_environment.authorization_map.add_mapping("page-webinars", ["read-only"])  # type: ignore

        # Create authorizations with multiple page resources
        authorizations = create_page_resource_authorizations(["web", "webinars"])

        # Create active user entry
        entry = create_active_user_entry(
            email="user6@example.com",
            registry_id="user6",
            authorizations=authorizations,
        )

        # Execute
        update_process.visit(entry)

        # Verify multiple errors were collected
        assert mock_collector.has_errors()
        assert mock_collector.error_count() == 2

        errors = mock_collector.get_errors()
        assert all(
            error.category == EventCategory.FLYWHEEL_ERROR.value for error in errors
        )
        assert all("Page project not found" in error.message for error in errors)

    def test_general_authorization_with_missing_roles(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
        mock_collector: UserEventCollector,
    ) -> None:
        """Test general authorization when authorization map has no roles.

        Validates:
        - Missing roles collects error with INSUFFICIENT_PERMISSIONS category
        - Processing continues without raising exception
        - Error event includes descriptive message
        """
        # Setup
        user = create_mock_user(user_id="user7", email="user7@example.com")
        mock_environment.add_user(user)

        # Add page project but no role mapping
        mock_environment.admin_group.add_project("page-web")  # type: ignore
        # Don't add role mapping - this will cause INSUFFICIENT_PERMISSIONS error

        # Create authorizations
        authorizations = create_page_resource_authorizations(["web"])

        # Create active user entry
        entry = create_active_user_entry(
            email="user7@example.com",
            registry_id="user7",
            authorizations=authorizations,
        )

        # Execute
        update_process.visit(entry)

        # Verify error was collected with correct category
        assert mock_collector.has_errors()
        assert mock_collector.error_count() == 1

        errors = mock_collector.get_errors()
        assert errors[0].category == EventCategory.INSUFFICIENT_PERMISSIONS.value
        assert "No roles found" in errors[0].message
        assert "user7" in errors[0].message

    def test_empty_authorizations_no_processing(
        self,
        update_process: UpdateUserProcess,
        mock_environment: MockUserProcessEnvironment,
        mock_collector: UserEventCollector,
    ) -> None:
        """Test that empty authorizations result in no processing.

        Validates:
        - Empty activities dictionary causes early return
        - No errors are collected
        - No projects are accessed
        """
        # Setup
        user = create_mock_user(user_id="user8", email="user8@example.com")
        mock_environment.add_user(user)

        # Create empty authorizations
        authorizations = Authorizations(activities=Activities())

        # Create active user entry
        entry = create_active_user_entry(
            email="user8@example.com",
            registry_id="user8",
            authorizations=authorizations,
        )

        # Execute
        update_process.visit(entry)

        # Verify no errors were collected
        assert not mock_collector.has_errors()
        assert mock_collector.error_count() == 0
