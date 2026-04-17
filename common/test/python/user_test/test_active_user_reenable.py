"""Unit tests for ActiveUserProcess re-enable logic.

Tests that the ActiveUserProcess correctly re-enables suspended
RegistryPerson records matched by email, collects appropriate events,
and preserves existing claimed/unclaimed routing for non-suspended
persons.
"""

import logging
from typing import Optional
from unittest.mock import Mock

import pytest
from users.authorizations import Authorizations
from users.event_models import (
    EventCategory,
    EventType,
    UserEventCollector,
)
from users.user_entry import CenterUserEntry, PersonName
from users.user_processes import ActiveUserProcess, UserProcessEnvironment
from users.user_registry import RegistryError, RegistryPerson


class TestActiveUserProcessReEnable:
    """Unit tests for ActiveUserProcess suspended-user re-enable logic."""

    @pytest.fixture
    def mock_environment(self):
        """Create a mock UserProcessEnvironment."""
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_env.user_registry = Mock()
        mock_env.notification_client = Mock()

        mock_env.find_user = Mock(return_value=None)
        mock_env.get_from_registry = Mock(
            side_effect=lambda email: mock_env.user_registry.get(email=email)
        )

        # Default: no domain/name candidates
        mock_env.user_registry.get_by_parent_domain = Mock(return_value=[])
        mock_env.user_registry.get_by_name = Mock(return_value=[])

        return mock_env

    @pytest.fixture
    def collector(self):
        """Create a UserEventCollector."""
        return UserEventCollector()

    @pytest.fixture
    def sample_active_entry(self):
        """Create a sample CenterUserEntry for testing."""
        return CenterUserEntry(
            name=PersonName(first_name="Alice", last_name="Smith"),
            email="alice@example.com",
            auth_email="alice.auth@example.com",
            active=True,
            approved=True,
            org_name="Test Center",
            adcid=100,
            authorizations=Authorizations(),
            study_authorizations=[],
        )

    def _make_suspended_person(self, registry_id: Optional[str] = "NACC-001") -> Mock:
        """Create a mock suspended RegistryPerson."""
        person = Mock(spec=RegistryPerson)
        person.is_suspended.return_value = True
        person.is_claimed.return_value = False
        person.registry_id.return_value = registry_id
        person.creation_date = None
        return person

    def _make_active_person(
        self,
        registry_id: str = "NACC-002",
        claimed: bool = True,
    ) -> Mock:
        """Create a mock active (non-suspended) RegistryPerson."""
        person = Mock(spec=RegistryPerson)
        person.is_suspended.return_value = False
        person.is_claimed.return_value = claimed
        person.registry_id.return_value = registry_id
        person.creation_date = "2024-01-01"
        return person

    def test_suspended_person_is_re_enabled(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that a suspended RegistryPerson matched by email is re-
        enabled."""
        suspended = self._make_suspended_person("NACC-001")
        mock_environment.user_registry.get.return_value = [suspended]

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        mock_environment.user_registry.re_enable.assert_called_once_with("NACC-001")

    def test_add_not_called_when_suspended_match_exists(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that add is not called when a suspended match exists."""
        suspended = self._make_suspended_person("NACC-001")
        mock_environment.user_registry.get.return_value = [suspended]

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        mock_environment.user_registry.add.assert_not_called()

    def test_success_event_collected_on_re_enable(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that a success event is collected on successful re-enable."""
        suspended = self._make_suspended_person("NACC-001")
        mock_environment.user_registry.get.return_value = [suspended]

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        successes = collector.get_successes()
        assert len(successes) == 1

        event = successes[0]
        assert event.event_type == EventType.SUCCESS.value
        assert event.category == EventCategory.USER_RE_ENABLED.value
        assert "NACC-001" in event.message
        assert "re-enabled" in event.message

    def test_error_event_collected_on_re_enable_failure(
        self, mock_environment, collector, sample_active_entry, caplog
    ):
        """Test that an error event is collected on re-enable failure and
        processing continues."""
        suspended = self._make_suspended_person("NACC-001")
        mock_environment.user_registry.get.return_value = [suspended]
        mock_environment.user_registry.re_enable.side_effect = RegistryError(
            "API update_co_person call failed: 500"
        )

        process = ActiveUserProcess(mock_environment, collector)

        with caplog.at_level(logging.ERROR):
            process.visit(sample_active_entry)

        errors = collector.get_errors()
        assert len(errors) == 1

        error_event = errors[0]
        assert error_event.event_type == EventType.ERROR.value
        assert error_event.category == EventCategory.USER_RE_ENABLED.value
        assert "NACC-001" in error_event.message
        assert "Failed to re-enable" in error_event.message

    def test_active_person_follows_claimed_flow(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that active (non-suspended) claimed persons follow the existing
        claimed flow."""
        active_person = self._make_active_person("NACC-002", claimed=True)
        mock_environment.user_registry.get.return_value = [active_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        # re_enable should NOT be called for active persons
        mock_environment.user_registry.re_enable.assert_not_called()

        # The entry should be registered with the claimed person
        assert sample_active_entry.is_registered
        assert sample_active_entry.registry_person == active_person

    def test_active_person_follows_unclaimed_flow(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that active (non-suspended) unclaimed persons follow the
        existing unclaimed flow."""
        unclaimed_person = self._make_active_person("NACC-003", claimed=False)
        unclaimed_person.is_claimed.return_value = False
        mock_environment.user_registry.get.return_value = [unclaimed_person]
        mock_environment.user_registry.has_bad_claim.return_value = False

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        # re_enable should NOT be called for active persons
        mock_environment.user_registry.re_enable.assert_not_called()
        # add should NOT be called (person exists)
        mock_environment.user_registry.add.assert_not_called()

    def test_multiple_suspended_persons_all_re_enabled(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that multiple suspended persons are all re-enabled."""
        suspended_1 = self._make_suspended_person("NACC-001")
        suspended_2 = self._make_suspended_person("NACC-002")
        mock_environment.user_registry.get.return_value = [
            suspended_1,
            suspended_2,
        ]

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        assert mock_environment.user_registry.re_enable.call_count == 2
        mock_environment.user_registry.re_enable.assert_any_call("NACC-001")
        mock_environment.user_registry.re_enable.assert_any_call("NACC-002")

        successes = collector.get_successes()
        assert len(successes) == 2

    def test_suspended_person_without_registry_id_skipped(
        self, mock_environment, collector, sample_active_entry
    ):
        """Test that a suspended person without a registry ID is skipped."""
        suspended_no_id = self._make_suspended_person(registry_id=None)
        mock_environment.user_registry.get.return_value = [suspended_no_id]

        process = ActiveUserProcess(mock_environment, collector)
        process.visit(sample_active_entry)

        mock_environment.user_registry.re_enable.assert_not_called()
