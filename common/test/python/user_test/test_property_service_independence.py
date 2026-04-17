"""Property test for Flywheel/COmanage service independence.

**Feature: disable-inactive-comanage-users, Property 2: Flywheel disable and
COmanage suspend are independent**
**Validates: Requirements 3.1, 3.3, 3.4**
"""

from unittest.mock import Mock

from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy
from hypothesis import given, settings
from hypothesis import strategies as st
from users.event_models import UserEventCollector
from users.user_entry import PersonName, UserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_processes import InactiveUserProcess
from users.user_registry import RegistryError, RegistryPerson, UserRegistry

# --- Fast strategies ---

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
def _inactive_user_entry_strategy(draw):
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
def _mock_fw_user_list_strategy(draw):
    """Generate a list of mock Flywheel User objects (0 to 3)."""
    count = draw(st.integers(min_value=0, max_value=3))
    users = []
    for i in range(count):
        user_id = f"fw-user-{i}-{draw(st.integers(min_value=100, max_value=999))}"
        user = Mock(spec=User)
        user.id = user_id
        user.email = f"user{i}@example.com"
        users.append(user)
    return users


@st.composite
def _mock_registry_person_list_strategy(draw):
    """Generate a list of mock RegistryPerson objects (0 to 3)."""
    count = draw(st.integers(min_value=0, max_value=3))
    persons = []
    for _ in range(count):
        person = Mock(spec=RegistryPerson)
        registry_id = f"NACC-{draw(st.integers(min_value=1000, max_value=9999))}"
        person.registry_id.return_value = registry_id
        person.is_suspended.return_value = False
        persons.append(person)
    return persons


# --- Property test ---


@given(
    entry=_inactive_user_entry_strategy(),
    fw_users=_mock_fw_user_list_strategy(),
    registry_persons=_mock_registry_person_list_strategy(),
    flywheel_fails=st.booleans(),
    comanage_fails=st.booleans(),
)
@settings(max_examples=100)
def test_flywheel_and_comanage_are_independent(
    entry: UserEntry,
    fw_users: list,
    registry_persons: list,
    flywheel_fails: bool,
    comanage_fails: bool,
):
    """Property 2: Flywheel disable and COmanage suspend are independent.

    **Feature: disable-inactive-comanage-users, Property 2: Flywheel disable
    and COmanage suspend are independent**
    **Validates: Requirements 3.1, 3.3, 3.4**

    For any inactive user entry and any combination of Flywheel and COmanage
    operation outcomes (success or failure), the failure of one service
    operation does not prevent the other from being attempted.
    """
    # Arrange
    mock_env = Mock(spec=UserProcessEnvironment)
    mock_proxy = Mock(spec=FlywheelProxy)
    mock_registry = Mock(spec=UserRegistry)

    mock_proxy.find_user_by_email.return_value = fw_users
    mock_registry.get.return_value = registry_persons

    if flywheel_fails and fw_users:
        mock_proxy.disable_user.side_effect = FlywheelError("Flywheel error")

    if comanage_fails and registry_persons:
        mock_registry.suspend.side_effect = RegistryError("COmanage error")

    mock_env.proxy = mock_proxy
    mock_env.user_registry = mock_registry

    collector = UserEventCollector()
    process = InactiveUserProcess(mock_env, collector)

    # Act
    process.visit(entry)

    # Assert: Flywheel lookup always happens
    mock_proxy.find_user_by_email.assert_called_once_with(entry.email)

    # Assert: COmanage lookup always happens (regardless of Flywheel outcome)
    mock_registry.get.assert_called_once_with(email=entry.email)

    # Assert: Flywheel disable is attempted for each user
    if fw_users:
        assert mock_proxy.disable_user.call_count == len(fw_users)
    else:
        mock_proxy.disable_user.assert_not_called()

    # Assert: COmanage suspend is attempted for each person with a registry ID
    # (regardless of whether Flywheel succeeded or failed)
    expected_suspend_count = sum(
        1 for p in registry_persons if p.registry_id() is not None
    )
    if expected_suspend_count > 0:
        assert mock_registry.suspend.call_count == expected_suspend_count
    else:
        mock_registry.suspend.assert_not_called()
