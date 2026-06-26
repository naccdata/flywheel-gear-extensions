"""Integration tests for profile sync in user processes.

Tests fault isolation between profile sync and grant sync, and verifies
that InactiveUserProcess continues remaining steps after profile sync failure.

Validates: Requirements 3.6, 4.3, 4.4
"""

import logging
from unittest.mock import Mock

from centers.center_info import CenterMapInfo
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from users.authorizations import Authorizations
from users.event_models import UserEventCollector
from users.user_entry import ActiveUserEntry, PersonName, UserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_processes import InactiveUserProcess, UpdateUserProcess
from users.user_registry import RegistryPerson, UserRegistry


def _build_mock_env(
    *,
    authorization_sync: Mock | None = None,
) -> Mock:
    """Build a mock UserProcessEnvironment with sensible defaults."""
    mock_env = Mock(spec=UserProcessEnvironment)
    mock_env.proxy = Mock(spec=FlywheelProxy)
    mock_env.proxy.dry_run = False
    mock_env.proxy.find_user_by_email.return_value = []
    mock_env.user_registry = Mock(spec=UserRegistry)
    mock_env.user_registry.get.return_value = []
    mock_env.admin_group = Mock()
    mock_env.admin_group.get_center_map.return_value = CenterMapInfo(centers={})
    mock_env.authorization_map = Mock()
    mock_env.authorization_sync = authorization_sync
    mock_env.notification_client = Mock()
    mock_env.find_user = Mock(return_value=None)
    return mock_env


def _build_registry_person(
    registry_id: str = "Registry000001@naccdata.org",
    suspended: bool = False,
) -> Mock:
    """Build a mock RegistryPerson."""
    person = Mock(spec=RegistryPerson)
    person.registry_id.return_value = registry_id
    person.is_suspended.return_value = suspended
    person.is_claimed.return_value = True
    person.creation_date = "2024-01-01"
    person.email_address = Mock()
    person.email_address.mail = "user@example.com"
    return person


def _build_active_entry() -> ActiveUserEntry:
    """Build an ActiveUserEntry for testing."""
    entry = ActiveUserEntry(
        name=PersonName(first_name="John", last_name="Doe"),
        email="john.doe@example.com",
        auth_email="john.auth@example.com",
        active=True,
        approved=True,
        authorizations=Authorizations(),
    )
    person = _build_registry_person()
    entry.register(person)
    return entry


def _build_inactive_entry() -> UserEntry:
    """Build an inactive UserEntry for testing."""
    return UserEntry(
        name=PersonName(first_name="Jane", last_name="Smith"),
        email="jane.smith@example.com",
        auth_email="jane.auth@example.com",
        active=False,
        approved=True,
    )


class TestUpdateUserProcessFaultIsolation:
    """Tests that profile sync and grant sync are independent in
    UpdateUserProcess."""

    def test_profile_sync_failure_does_not_block_grant_sync(self, caplog) -> None:
        """Profile sync failure does not prevent grant sync from completing.

        Validates: Requirements 3.6
        """
        mock_sync = Mock()
        # grant sync succeeds
        mock_sync.sync_user.return_value = None
        # profile sync fails
        mock_sync.sync_profile.side_effect = Exception("Profile API down")

        mock_env = _build_mock_env(authorization_sync=mock_sync)

        entry = _build_active_entry()
        fw_user = Mock(spec=User)
        fw_user.id = "Registry000001@naccdata.org"
        fw_user.email = "john.doe@example.com"
        mock_env.find_user.return_value = fw_user

        collector = UserEventCollector()
        process = UpdateUserProcess(mock_env, collector)

        with caplog.at_level(logging.ERROR):
            process.visit(entry)

        # Grant sync was called and completed successfully
        mock_sync.sync_user.assert_called_once()
        # Profile sync was attempted (and failed)
        mock_sync.sync_profile.assert_called_once()
        # Error was logged but did not propagate
        assert "Profile sync failed" in caplog.text

    def test_grant_sync_failure_does_not_block_profile_sync(self, caplog) -> None:
        """Grant sync failure does not prevent profile sync from completing.

        Validates: Requirements 3.6
        """
        mock_sync = Mock()
        # grant sync fails
        mock_sync.sync_user.side_effect = Exception("Grant API down")
        # profile sync succeeds
        mock_sync.sync_profile.return_value = None

        mock_env = _build_mock_env(authorization_sync=mock_sync)

        entry = _build_active_entry()
        fw_user = Mock(spec=User)
        fw_user.id = "Registry000001@naccdata.org"
        fw_user.email = "john.doe@example.com"
        mock_env.find_user.return_value = fw_user

        collector = UserEventCollector()
        process = UpdateUserProcess(mock_env, collector)

        with caplog.at_level(logging.ERROR):
            process.visit(entry)

        # Grant sync was attempted (and failed)
        mock_sync.sync_user.assert_called_once()
        # Profile sync was still called and completed
        mock_sync.sync_profile.assert_called_once()
        # Error was logged but did not propagate
        assert "Authorization sync failed" in caplog.text


class TestInactiveUserProcessProfileSync:
    """Tests for profile sync integration in InactiveUserProcess."""

    def test_continues_remaining_steps_after_profile_sync_failure(self, caplog) -> None:
        """InactiveUserProcess continues with REDCap disable and COmanage
        suspend after profile sync failure.

        Validates: Requirements 4.3, 4.4
        """
        mock_sync = Mock()
        mock_sync.sync_profile.side_effect = Exception("Profile API down")

        mock_env = _build_mock_env(authorization_sync=mock_sync)

        # Setup COmanage lookup to return a person (so profile sync is attempted)
        person = _build_registry_person(
            registry_id="Registry000001@naccdata.org",
            suspended=False,
        )
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_inactive_entry()

        with caplog.at_level(logging.ERROR):
            process.visit(entry)

        # Profile sync was attempted and failed
        mock_sync.sync_profile.assert_called_once()
        assert "Profile sync failed" in caplog.text

        # Step 4 (COmanage suspend) was still executed
        mock_env.user_registry.suspend.assert_called_once_with(
            "Registry000001@naccdata.org"
        )

    def test_profile_sync_skipped_when_registry_id_is_none(self, caplog) -> None:
        """Profile sync is skipped when no person_list is found (registry_id is
        None).

        Validates: Requirements 4.3
        """
        mock_sync = Mock()
        mock_env = _build_mock_env(authorization_sync=mock_sync)

        # No COmanage records found — person_list is empty
        mock_env.user_registry.get.return_value = []

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_inactive_entry()

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Profile sync was NOT called because registry_id is None
        mock_sync.sync_profile.assert_not_called()

    def test_profile_sync_skipped_when_person_has_no_registry_id(self, caplog) -> None:
        """Profile sync is skipped when person_list exists but registry_id
        returns None.

        Validates: Requirements 4.3
        """
        mock_sync = Mock()
        mock_env = _build_mock_env(authorization_sync=mock_sync)

        # Person exists but has no registry_id
        person = Mock(spec=RegistryPerson)
        person.registry_id.return_value = None
        person.is_suspended.return_value = False
        person.email_address = Mock()
        person.email_address.mail = "jane@example.com"
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_inactive_entry()

        with caplog.at_level(logging.INFO):
            process.visit(entry)

        # Profile sync was NOT called because registry_id is None
        mock_sync.sync_profile.assert_not_called()
