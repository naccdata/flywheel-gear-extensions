"""Tests to verify that ActiveUserEntry and CenterUserEntry are handled
differently in user processes.

These tests ensure that:
1. UpdateUserProcess handles both ActiveUserEntry and CenterUserEntry
2. CenterUserEntry gets routed to UpdateCenterUserProcess for authorization
3. ActiveUserEntry does NOT get routed to UpdateCenterUserProcess
4. The fw_user field is set correctly for both types
"""

import logging
from unittest.mock import Mock

import pytest
from users.authorizations import Authorizations, StudyAuthorizations
from users.event_models import UserEventCollector
from users.user_entry import ActiveUserEntry, CenterUserEntry, PersonName
from users.user_processes import (
    UpdateCenterUserProcess,
    UpdateUserProcess,
    UserProcessEnvironment,
    UserQueue,
)
from users.user_registry import RegistryPerson


class TestActiveUserEntryVsCenterUserEntry:
    """Tests to verify different handling of ActiveUserEntry vs
    CenterUserEntry."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment for testing."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.proxy = Mock()
        mock_env.admin_group = Mock()
        mock_env.authorization_map = Mock()

        # Configure wrapper methods
        mock_env.find_user = Mock(
            side_effect=lambda user_id: mock_env.proxy.find_user(user_id)
        )
        mock_env.add_user = Mock(side_effect=lambda user: mock_env.proxy.add_user(user))
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )

        return mock_env

    @pytest.fixture
    def collector(self):
        """Create a UserEventCollector for testing."""
        return UserEventCollector()

    @pytest.fixture
    def active_user_entry(self):
        """Create a registered ActiveUserEntry (not a CenterUserEntry)."""
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "active123"

        entry = ActiveUserEntry(
            name=PersonName(first_name="Active", last_name="User"),
            email="active.user@example.com",
            auth_email="active.auth@example.com",
            active=True,
            approved=True,
            authorizations=Authorizations(),
        )
        entry.register(mock_registry_person)
        return entry

    @pytest.fixture
    def center_user_entry(self):
        """Create a registered CenterUserEntry."""
        mock_registry_person = Mock(spec=RegistryPerson)
        mock_registry_person.registry_id.return_value = "center456"
        mock_registry_person.email_address = Mock()
        mock_registry_person.email_address.mail = "center.registry@example.com"

        entry = CenterUserEntry(
            name=PersonName(first_name="Center", last_name="User"),
            email="center.user@example.com",
            auth_email="center.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=123,
            authorizations=Authorizations(),
            study_authorizations=[
                StudyAuthorizations(study_id="study1", roles=["coordinator"])
            ],
        )
        entry.register(mock_registry_person)
        return entry

    def test_update_user_process_sets_fw_user_for_active_user_entry(
        self, mock_environment, collector, active_user_entry
    ):
        """Test that UpdateUserProcess sets fw_user for ActiveUserEntry."""
        mock_fw_user = Mock()
        mock_fw_user.id = "user123"
        mock_fw_user.email = active_user_entry.email

        mock_environment.proxy.find_user.return_value = mock_fw_user

        process = UpdateUserProcess(mock_environment, collector)
        process.visit(active_user_entry)

        # Verify fw_user was set on the entry
        assert active_user_entry.fw_user is not None
        assert active_user_entry.fw_user.id == "user123"

        # Verify no errors
        assert not collector.has_errors()

    def test_update_user_process_sets_fw_user_for_center_user_entry(
        self, mock_environment, collector, center_user_entry
    ):
        """Test that UpdateUserProcess sets fw_user for CenterUserEntry."""
        mock_fw_user = Mock()
        mock_fw_user.id = "user456"
        mock_fw_user.email = center_user_entry.email

        mock_environment.proxy.find_user.return_value = mock_fw_user

        process = UpdateUserProcess(mock_environment, collector)
        process.visit(center_user_entry)

        # Verify fw_user was set on the entry
        assert center_user_entry.fw_user is not None
        assert center_user_entry.fw_user.id == "user456"

        # Verify no errors
        assert not collector.has_errors()

    def test_update_user_process_routes_center_user_to_center_process(
        self, mock_environment, collector, center_user_entry, caplog
    ):
        """Test that CenterUserEntry is routed to UpdateCenterUserProcess."""
        mock_fw_user = Mock()
        mock_fw_user.id = "user456"
        mock_fw_user.email = center_user_entry.email

        mock_environment.proxy.find_user.return_value = mock_fw_user

        # Mock the center group for authorization
        mock_center_group = Mock()
        mock_environment.admin_group.get_center.return_value = mock_center_group
        mock_project_info = Mock()
        mock_center_group.get_project_info.return_value = mock_project_info

        # Create a queue and execute the full process
        queue: UserQueue[ActiveUserEntry] = UserQueue()
        queue.enqueue(center_user_entry)

        process = UpdateUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.execute(queue)

        # Verify center process was executed
        assert "**Update Flywheel users" in caplog.text
        assert "**Processing center users" in caplog.text

        # Verify center-specific methods were called
        mock_environment.admin_group.get_center.assert_called_once_with(123)
        mock_environment.admin_group.add_center_user.assert_called_once()

    def test_update_user_process_does_not_route_active_user_to_center_process(
        self, mock_environment, collector, active_user_entry, caplog
    ):
        """Test that ActiveUserEntry is NOT routed to
        UpdateCenterUserProcess."""
        mock_fw_user = Mock()
        mock_fw_user.id = "user123"
        mock_fw_user.email = active_user_entry.email

        mock_environment.proxy.find_user.return_value = mock_fw_user

        # Create a queue and execute the full process
        queue: UserQueue[ActiveUserEntry] = UserQueue()
        queue.enqueue(active_user_entry)

        process = UpdateUserProcess(mock_environment, collector)

        with caplog.at_level(logging.INFO):
            process.execute(queue)

        # Verify UpdateUserProcess was executed
        assert "**Update Flywheel users" in caplog.text

        # Verify center process was executed but did nothing
        # (it runs but the queue is empty)
        assert "**Processing center users" in caplog.text

        # Verify center-specific methods were NOT called
        mock_environment.admin_group.get_center.assert_not_called()
        mock_environment.admin_group.add_center_user.assert_not_called()

    def test_update_center_user_process_only_accepts_center_users(
        self, mock_environment, collector, center_user_entry
    ):
        """Test that UpdateCenterUserProcess processes CenterUserEntry with
        center-specific logic."""
        # Set up the entry with fw_user
        mock_fw_user = Mock()
        mock_fw_user.id = "user456"
        mock_fw_user.email = center_user_entry.email
        center_user_entry.set_fw_user(mock_fw_user)

        # Mock the center group
        mock_center_group = Mock()
        mock_environment.admin_group.get_center.return_value = mock_center_group
        mock_project_info = Mock()
        mock_center_group.get_project_info.return_value = mock_project_info

        process = UpdateCenterUserProcess(mock_environment, collector)
        process.visit(center_user_entry)

        # Verify center-specific operations were performed
        mock_environment.admin_group.get_center.assert_called_once_with(123)
        mock_environment.admin_group.add_center_user.assert_called_once_with(
            user=mock_fw_user
        )
        mock_center_group.get_project_info.assert_called_once()
        mock_project_info.apply.assert_called_once()

        # Verify no errors
        assert not collector.has_errors()

    def test_isinstance_check_correctly_identifies_center_user(
        self, center_user_entry, active_user_entry
    ):
        """Test that isinstance correctly identifies CenterUserEntry vs
        ActiveUserEntry."""
        # CenterUserEntry should be an instance of both
        assert isinstance(center_user_entry, CenterUserEntry)
        assert isinstance(center_user_entry, ActiveUserEntry)

        # ActiveUserEntry should NOT be an instance of CenterUserEntry
        assert not isinstance(active_user_entry, CenterUserEntry)
        assert isinstance(active_user_entry, ActiveUserEntry)

    def test_center_user_has_additional_fields(
        self, center_user_entry, active_user_entry
    ):
        """Test that CenterUserEntry has fields that ActiveUserEntry doesn't
        have."""
        # CenterUserEntry has these fields
        assert hasattr(center_user_entry, "org_name")
        assert hasattr(center_user_entry, "adcid")
        assert hasattr(center_user_entry, "study_authorizations")
        assert center_user_entry.org_name == "Test Center"
        assert center_user_entry.adcid == 123
        assert len(center_user_entry.study_authorizations) == 1

        # ActiveUserEntry does not have these fields
        assert not hasattr(active_user_entry, "org_name")
        assert not hasattr(active_user_entry, "adcid")
        assert not hasattr(active_user_entry, "study_authorizations")

    def test_both_types_have_common_fields(self, center_user_entry, active_user_entry):
        """Test that both types have common ActiveUserEntry fields."""
        # Both should have these fields
        for entry in [center_user_entry, active_user_entry]:
            assert hasattr(entry, "name")
            assert hasattr(entry, "email")
            assert hasattr(entry, "auth_email")
            assert hasattr(entry, "active")
            assert hasattr(entry, "approved")
            assert hasattr(entry, "authorizations")
            assert hasattr(entry, "registry_person")
            assert hasattr(entry, "fw_user")
