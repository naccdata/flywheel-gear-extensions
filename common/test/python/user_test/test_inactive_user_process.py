"""Property tests and unit tests for InactiveUserProcess.

Tests Property 1 from the disable-inactive-users design document, and
unit tests for COmanage suspension behavior.
"""

from unittest.mock import Mock, call

from centers.center_info import CenterMapInfo
from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy
from hypothesis import given, settings
from hypothesis import strategies as st
from users.event_models import EventCategory, EventType, UserEventCollector
from users.user_entry import PersonName, UserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_processes import InactiveUserProcess
from users.user_registry import RegistryError, RegistryPerson, UserRegistry

# Fast email strategy: avoids the slow st.emails() for property tests
# where the actual email content doesn't matter, only its presence.
_fast_email = st.builds(
    lambda user, domain: f"{user}@{domain}.com",
    st.text(
        alphabet=st.characters(whitelist_categories=["Ll"]),
        min_size=1,
        max_size=8,
    ),
    st.text(
        alphabet=st.characters(whitelist_categories=["Ll"]),
        min_size=1,
        max_size=8,
    ),
)

_letters = st.characters(whitelist_categories=("Lu", "Ll"))


@st.composite
def inactive_user_entry_strategy(draw):
    """Generate inactive UserEntry objects."""
    first_name = draw(st.text(min_size=1, max_size=20, alphabet=_letters))
    last_name = draw(st.text(min_size=1, max_size=20, alphabet=_letters))
    email = draw(_fast_email)
    return UserEntry(
        name=PersonName(first_name=first_name, last_name=last_name),
        email=email,
        active=False,
        approved=draw(st.booleans()),
    )


@st.composite
def mock_fw_user_list_strategy(draw):
    """Generate a list of mock Flywheel User objects."""
    count = draw(st.integers(min_value=0, max_value=5))
    users = []
    for i in range(count):
        user_id = f"fw-user-{i}-{draw(st.integers(min_value=100, max_value=999))}"
        email = draw(_fast_email)
        user = Mock(spec=User)
        user.id = user_id
        user.email = email
        users.append(user)
    return users


class TestInactiveEntryProcessingProperty:
    """Property 1: Inactive entry processing disables all matching Flywheel
    users.

    Feature: disable-inactive-users, Property 1: Inactive entry processing
    disables all matching Flywheel users.
    """

    @given(
        entry=inactive_user_entry_strategy(),
        fw_users=mock_fw_user_list_strategy(),
    )
    @settings(max_examples=100)
    def test_visit_disables_all_matching_users(
        self, entry: UserEntry, fw_users: list
    ) -> None:
        """For any inactive UserEntry and any list of matching Flywheel users,
        disable_user is called exactly once per match.

        When the match list is empty, disable_user is not called.
        """
        mock_env = Mock(spec=UserProcessEnvironment)
        mock_proxy = Mock(spec=FlywheelProxy)
        mock_proxy.find_user_by_email.return_value = fw_users
        mock_env.proxy = mock_proxy
        mock_env.proxy.dry_run = False
        mock_env.user_registry.get.return_value = []
        mock_env.admin_group.get_center_map.return_value = CenterMapInfo(centers={})

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)

        process.visit(entry)

        mock_proxy.find_user_by_email.assert_called_once_with(entry.email)

        if not fw_users:
            mock_proxy.disable_user.assert_not_called()
        else:
            assert mock_proxy.disable_user.call_count == len(fw_users)
            expected_calls = [call(user) for user in fw_users]
            mock_proxy.disable_user.assert_has_calls(expected_calls, any_order=False)


# --- Unit tests for COmanage suspension in InactiveUserProcess ---
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7


def _build_entry(email: str = "user@example.com") -> UserEntry:
    """Build an inactive UserEntry for testing."""
    return UserEntry(
        name=PersonName(first_name="Test", last_name="User"),
        email=email,
        active=False,
        approved=True,
    )


def _build_mock_env() -> Mock:
    """Build a mock UserProcessEnvironment with sensible defaults."""
    mock_env = Mock(spec=UserProcessEnvironment)
    mock_env.proxy = Mock(spec=FlywheelProxy)
    mock_env.proxy.find_user_by_email.return_value = []
    mock_env.proxy.dry_run = False
    mock_env.user_registry = Mock(spec=UserRegistry)
    mock_env.user_registry.get.return_value = []
    mock_env.admin_group.get_center_map.return_value = CenterMapInfo(centers={})
    return mock_env


def _build_fw_user(user_id: str = "fw-user-1") -> Mock:
    """Build a mock Flywheel User."""
    user = Mock(spec=User)
    user.id = user_id
    user.email = "user@example.com"
    return user


def _build_registry_person(
    registry_id: str = "NACC-001",
    suspended: bool = False,
) -> Mock:
    """Build a mock RegistryPerson with a registry ID."""
    person = Mock(spec=RegistryPerson)
    person.registry_id.return_value = registry_id
    person.is_suspended.return_value = suspended
    return person


class TestInactiveUserComanageSuspension:
    """Unit tests for COmanage suspension in InactiveUserProcess."""

    def test_comanage_suspend_attempted_after_flywheel_disable(self) -> None:
        """COmanage suspend is attempted after Flywheel disable succeeds."""
        mock_env = _build_mock_env()
        fw_user = _build_fw_user()
        mock_env.proxy.find_user_by_email.return_value = [fw_user]

        person = _build_registry_person("NACC-001")
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # Flywheel disable was called
        mock_env.proxy.disable_user.assert_called_once_with(fw_user)
        # COmanage suspend was called
        mock_env.user_registry.suspend.assert_called_once_with("NACC-001")

    def test_comanage_suspend_attempted_when_flywheel_disable_fails(self) -> None:
        """COmanage suspend is still attempted even when Flywheel disable
        fails."""
        mock_env = _build_mock_env()
        fw_user = _build_fw_user()
        mock_env.proxy.find_user_by_email.return_value = [fw_user]
        mock_env.proxy.disable_user.side_effect = FlywheelError("Flywheel down")

        person = _build_registry_person("NACC-002")
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        # Flywheel disable was attempted (and failed)
        mock_env.proxy.disable_user.assert_called_once_with(fw_user)
        # COmanage suspend was still attempted
        mock_env.user_registry.suspend.assert_called_once_with("NACC-002")

    def test_no_error_when_no_comanage_record_found(self) -> None:
        """No error when no COmanage record found for user email."""
        mock_env = _build_mock_env()
        mock_env.proxy.find_user_by_email.return_value = []
        mock_env.user_registry.get.return_value = []

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        # Should not raise
        process.visit(entry)

        mock_env.user_registry.suspend.assert_not_called()
        # No error events should be collected for missing COmanage records
        errors = collector.get_errors()
        comanage_errors = [
            e for e in errors if "COmanage" in e.message or "comanage" in e.message
        ]
        assert len(comanage_errors) == 0

    def test_success_event_collected_with_comanage_message(self) -> None:
        """Success event is collected with COmanage-specific message on
        suspend."""
        mock_env = _build_mock_env()
        mock_env.proxy.find_user_by_email.return_value = []

        person = _build_registry_person("NACC-003")
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        successes = collector.get_successes()
        comanage_successes = [e for e in successes if "COmanage" in e.message]
        assert len(comanage_successes) == 1

        event = comanage_successes[0]
        assert event.message == "User NACC-003 suspended in COmanage"
        assert event.category == EventCategory.COMANAGE_USER_SUSPENDED.value
        assert event.event_type == EventType.SUCCESS.value

    def test_error_event_collected_when_comanage_suspend_fails(self) -> None:
        """Error event is collected when COmanage suspend fails."""
        mock_env = _build_mock_env()
        mock_env.proxy.find_user_by_email.return_value = []

        person = _build_registry_person("NACC-004")
        mock_env.user_registry.get.return_value = [person]
        mock_env.user_registry.suspend.side_effect = RegistryError(
            "API update_co_person call failed: 500"
        )

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        errors = collector.get_errors()
        comanage_errors = [e for e in errors if "COmanage" in e.message]
        assert len(comanage_errors) == 1

        event = comanage_errors[0]
        assert "NACC-004" in event.message
        assert "COmanage" in event.message
        assert event.category == EventCategory.COMANAGE_USER_SUSPENDED.value
        assert event.event_type == EventType.ERROR.value

    def test_already_suspended_person_is_skipped(self) -> None:
        """A person already suspended in COmanage is not suspended again."""
        mock_env = _build_mock_env()
        mock_env.proxy.find_user_by_email.return_value = []

        person = _build_registry_person("NACC-005", suspended=True)
        mock_env.user_registry.get.return_value = [person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        mock_env.user_registry.suspend.assert_not_called()

    def test_mixed_suspended_and_active_persons(self) -> None:
        """Only non-suspended persons are suspended; already-suspended ones are
        skipped."""
        mock_env = _build_mock_env()
        mock_env.proxy.find_user_by_email.return_value = []

        already_suspended = _build_registry_person("NACC-006", suspended=True)
        active_person = _build_registry_person("NACC-007", suspended=False)
        mock_env.user_registry.get.return_value = [already_suspended, active_person]

        collector = UserEventCollector()
        process = InactiveUserProcess(mock_env, collector)
        entry = _build_entry()

        process.visit(entry)

        mock_env.user_registry.suspend.assert_called_once_with("NACC-007")
