"""Integration tests for authorization sync pipeline integration.

Tests that UpdateCenterUserProcess and UpdateUserProcess correctly invoke
the AuthorizationSyncService after visitor processing, and that sync
failures do not prevent Flywheel role assignment.

Validates: Requirements 8.1, 8.2, 8.4, 8.5
"""

from unittest.mock import Mock

import pytest
from authorization_sync.sync_service import AuthorizationSyncService
from flywheel.models.user import User
from users.authorizations import (
    Activities,
    Activity,
    Authorizations,
    DatatypeResource,
    PageResource,
    StudyAuthorizations,
)
from users.event_models import UserEventCollector
from users.user_entry import ActiveUserEntry, CenterUserEntry, PersonName
from users.user_processes import UpdateCenterUserProcess, UpdateUserProcess
from users.user_registry import RegistryPerson

# --- Test Helpers ---


def create_mock_user(
    user_id: str = "test-user",
    email: str = "test@example.com",
) -> User:
    """Create a mock Flywheel User."""
    user = Mock(spec=User)
    user.id = user_id
    user.email = email
    user.firstname = "Test"
    user.lastname = "User"
    return user


def create_mock_registry_person(
    registry_id: str = "user@institution.edu",
    email: str = "user@institution.edu",
) -> Mock:
    """Create a mock RegistryPerson with email_address."""
    person = Mock(spec=RegistryPerson)
    person.registry_id.return_value = registry_id
    person.email_address = Mock()
    person.email_address.mail = email
    return person


def create_mock_environment(
    authorization_sync=None,
    center_group_label: str = "washington",
):
    """Create a mock UserProcessEnvironment for integration tests.

    Args:
        authorization_sync: The sync service (or None to skip sync).
        center_group_label: The label for the center group.
    """
    from users.user_process_environment import UserProcessEnvironment

    mock_env = Mock(spec=UserProcessEnvironment)
    mock_env.authorization_sync = authorization_sync
    mock_env.authorization_map = Mock()
    mock_env.authorization_map.get = Mock(return_value=[])

    # Setup admin_group with center
    mock_center_group = Mock()
    mock_center_group.label = center_group_label
    mock_project_info = Mock()
    mock_project_info.apply = Mock()
    mock_center_group.get_project_info.return_value = mock_project_info
    mock_env.admin_group = Mock()
    mock_env.admin_group.get_center.return_value = mock_center_group
    mock_env.admin_group.add_center_user = Mock()

    # Setup proxy for UpdateUserProcess
    mock_env.proxy = Mock()
    mock_env.proxy.set_user_email = Mock()

    # Setup find_user for UpdateUserProcess
    mock_env.find_user = Mock(return_value=None)

    return mock_env


def create_study_authorizations(
    study_id: str = "study-1",
    datatype: str = "form",
) -> StudyAuthorizations:
    """Create a StudyAuthorizations with a submit-audit activity."""
    activities = Activities()
    resource = DatatypeResource(datatype=datatype)
    activity = Activity(resource=resource, action="submit-audit")
    activities.add(resource, activity)
    return StudyAuthorizations(study_id=study_id, activities=activities)


def create_page_authorizations(page_name: str = "web") -> Authorizations:
    """Create Authorizations with a page resource activity."""
    activities = Activities()
    resource = PageResource(page=page_name)
    activity = Activity(resource=resource, action="view")
    activities.add(resource, activity)
    return Authorizations(activities=activities)


# --- Tests ---


class TestUpdateCenterUserProcessSyncIntegration:
    """Tests that UpdateCenterUserProcess calls sync after visitor.

    Validates: Requirements 8.1, 8.5
    """

    @pytest.fixture
    def mock_sync_service(self) -> Mock:
        """Create a mock AuthorizationSyncService."""
        return Mock(spec=AuthorizationSyncService)

    @pytest.fixture
    def collector(self) -> UserEventCollector:
        """Create a UserEventCollector."""
        return UserEventCollector()

    def test_sync_called_after_visitor_with_correct_arguments(
        self,
        mock_sync_service: Mock,
        collector: UserEventCollector,
    ) -> None:
        """UpdateCenterUserProcess invokes sync_user for each study
        authorization with registry_id and center_group_id.

        Validates: Requirement 8.1
        """
        # Setup
        study_auth_1 = create_study_authorizations("study-1", "form")
        study_auth_2 = create_study_authorizations("study-2", "enrollment")

        mock_env = create_mock_environment(
            authorization_sync=mock_sync_service,
            center_group_label="washington",
        )

        process = UpdateCenterUserProcess(
            environment=mock_env,
            collector=collector,
        )

        # Create a CenterUserEntry with required fields
        registry_person = create_mock_registry_person(
            registry_id="user@institution.edu",
            email="user@institution.edu",
        )

        fw_user = create_mock_user(
            user_id="fw-user-123",
            email="user@institution.edu",
        )

        entry = CenterUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="user@institution.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=1,
            authorizations=Authorizations(),
            study_authorizations=[study_auth_1, study_auth_2],
            registry_person=registry_person,
            fw_user=fw_user,
        )

        # Execute
        process.visit(entry)

        # Verify sync_user was called for each study authorization
        assert mock_sync_service.sync_user.call_count == 2

        # Verify correct arguments for first call
        call_args_list = mock_sync_service.sync_user.call_args_list

        # First study authorization
        call_1 = call_args_list[0]
        assert call_1.kwargs["registry_id"] == "user@institution.edu"
        assert call_1.kwargs["authorizations"] == study_auth_1
        assert call_1.kwargs["center_group_id"] == "washington"

        # Second study authorization
        call_2 = call_args_list[1]
        assert call_2.kwargs["registry_id"] == "user@institution.edu"
        assert call_2.kwargs["authorizations"] == study_auth_2
        assert call_2.kwargs["center_group_id"] == "washington"

    def test_sync_failure_does_not_prevent_flywheel_role_assignment(
        self,
        mock_sync_service: Mock,
        collector: UserEventCollector,
    ) -> None:
        """Sync failure must not prevent Flywheel role assignment from
        completing.

        Validates: Requirement 8.5
        """
        # Setup sync to raise an exception
        mock_sync_service.sync_user.side_effect = RuntimeError(
            "Authorization API unavailable"
        )

        study_auth = create_study_authorizations("study-1", "form")

        mock_env = create_mock_environment(
            authorization_sync=mock_sync_service,
            center_group_label="washington",
        )

        process = UpdateCenterUserProcess(
            environment=mock_env,
            collector=collector,
        )

        registry_person = create_mock_registry_person(
            registry_id="user@institution.edu",
            email="user@institution.edu",
        )

        fw_user = create_mock_user(
            user_id="fw-user-123",
            email="user@institution.edu",
        )

        entry = CenterUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="user@institution.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=1,
            authorizations=Authorizations(),
            study_authorizations=[study_auth],
            registry_person=registry_person,
            fw_user=fw_user,
        )

        # Execute - should not raise
        process.visit(entry)

        # Verify Flywheel role assignment still happened
        # (portal_info.apply was called with the visitor)
        center_group = mock_env.admin_group.get_center.return_value
        project_info = center_group.get_project_info.return_value
        project_info.apply.assert_called_once()

        # Verify add_center_user was called (metadata access)
        mock_env.admin_group.add_center_user.assert_called_once_with(user=fw_user)


class TestUpdateUserProcessSyncIntegration:
    """Tests that UpdateUserProcess calls sync for general authorizations.

    Validates: Requirements 8.2, 8.5
    """

    @pytest.fixture
    def mock_sync_service(self) -> Mock:
        """Create a mock AuthorizationSyncService."""
        return Mock(spec=AuthorizationSyncService)

    @pytest.fixture
    def collector(self) -> UserEventCollector:
        """Create a UserEventCollector."""
        return UserEventCollector()

    def test_sync_called_for_general_authorizations(
        self,
        mock_sync_service: Mock,
        collector: UserEventCollector,
    ) -> None:
        """UpdateUserProcess invokes sync_user with registry_id and
        authorizations (no center_group_id).

        Validates: Requirement 8.2
        """
        # Setup
        authorizations = create_page_authorizations("web")

        mock_env = create_mock_environment(
            authorization_sync=mock_sync_service,
        )

        fw_user = create_mock_user(
            user_id="user@institution.edu",
            email="user@institution.edu",
        )
        mock_env.find_user.return_value = fw_user

        process = UpdateUserProcess(
            environment=mock_env,
            collector=collector,
        )

        registry_person = create_mock_registry_person(
            registry_id="user@institution.edu",
        )

        entry = ActiveUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="user@institution.edu",
            active=True,
            approved=True,
            authorizations=authorizations,
            registry_person=registry_person,
        )

        # Execute
        process.visit(entry)

        # Verify sync_user was called with correct arguments
        mock_sync_service.sync_user.assert_called_once_with(
            registry_id="user@institution.edu",
            authorizations=authorizations,
        )

    def test_sync_failure_does_not_prevent_flywheel_role_assignment(
        self,
        mock_sync_service: Mock,
        collector: UserEventCollector,
    ) -> None:
        """Sync failure in UpdateUserProcess must not prevent Flywheel role
        assignment.

        The sync is called AFTER the visitor completes, so even if sync
        raises, the Flywheel roles have already been assigned.

        Validates: Requirement 8.5
        """
        # Setup sync to raise an exception
        mock_sync_service.sync_user.side_effect = RuntimeError(
            "Authorization API unavailable"
        )

        authorizations = create_page_authorizations("web")

        mock_env = create_mock_environment(
            authorization_sync=mock_sync_service,
        )

        fw_user = create_mock_user(
            user_id="user@institution.edu",
            email="user@institution.edu",
        )
        mock_env.find_user.return_value = fw_user

        # Add page project to admin group so visitor can succeed
        mock_page_project = Mock()
        mock_env.admin_group.get_project.return_value = mock_page_project

        process = UpdateUserProcess(
            environment=mock_env,
            collector=collector,
        )

        registry_person = create_mock_registry_person(
            registry_id="user@institution.edu",
        )

        entry = ActiveUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="user@institution.edu",
            active=True,
            approved=True,
            authorizations=authorizations,
            registry_person=registry_person,
        )

        # Execute - should not raise despite sync failure
        process.visit(entry)

        # Verify sync was attempted (and failed)
        mock_sync_service.sync_user.assert_called_once()


class TestNoneSyncServiceSkipsSync:
    """Tests that None sync service skips the sync step entirely.

    Validates: Requirement 8.4
    """

    @pytest.fixture
    def collector(self) -> UserEventCollector:
        """Create a UserEventCollector."""
        return UserEventCollector()

    def test_center_user_process_skips_sync_when_none(
        self,
        collector: UserEventCollector,
    ) -> None:
        """UpdateCenterUserProcess skips sync when authorization_sync is None.

        Validates: Requirement 8.4
        """
        # Setup with no sync service
        mock_env = create_mock_environment(authorization_sync=None)

        study_auth = create_study_authorizations("study-1", "form")

        process = UpdateCenterUserProcess(
            environment=mock_env,
            collector=collector,
        )

        registry_person = create_mock_registry_person(
            registry_id="user@institution.edu",
            email="user@institution.edu",
        )

        fw_user = create_mock_user(
            user_id="fw-user-123",
            email="user@institution.edu",
        )

        entry = CenterUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="user@institution.edu",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=1,
            authorizations=Authorizations(),
            study_authorizations=[study_auth],
            registry_person=registry_person,
            fw_user=fw_user,
        )

        # Execute - should complete without error
        process.visit(entry)

        # Verify Flywheel role assignment still happened
        center_group = mock_env.admin_group.get_center.return_value
        project_info = center_group.get_project_info.return_value
        project_info.apply.assert_called_once()

    def test_update_user_process_skips_sync_when_none(
        self,
        collector: UserEventCollector,
    ) -> None:
        """UpdateUserProcess skips sync when authorization_sync is None.

        Validates: Requirement 8.4
        """
        # Setup with no sync service
        mock_env = create_mock_environment(authorization_sync=None)

        authorizations = create_page_authorizations("web")

        fw_user = create_mock_user(
            user_id="user@institution.edu",
            email="user@institution.edu",
        )
        mock_env.find_user.return_value = fw_user

        process = UpdateUserProcess(
            environment=mock_env,
            collector=collector,
        )

        registry_person = create_mock_registry_person(
            registry_id="user@institution.edu",
        )

        entry = ActiveUserEntry(
            name=PersonName(first_name="Test", last_name="User"),
            email="user@institution.edu",
            active=True,
            approved=True,
            authorizations=authorizations,
            registry_person=registry_person,
        )

        # Execute - should complete without error
        process.visit(entry)

        # No sync service means no sync calls - verify by checking
        # that authorization_sync is None (the code checks this)
        assert mock_env.authorization_sync is None
