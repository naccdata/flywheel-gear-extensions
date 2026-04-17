"""Property test for re-enable instead of duplicate creation.

**Feature: disable-inactive-comanage-users, Property 3: Active process
re-enables suspended users instead of creating duplicates**
**Validates: Requirements 4.1, 4.2**
"""

from unittest.mock import Mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from users.authorizations import Authorizations
from users.event_models import UserEventCollector
from users.user_entry import CenterUserEntry, PersonName
from users.user_processes import ActiveUserProcess, UserProcessEnvironment
from users.user_registry import RegistryPerson

# --- Fast strategies ---

_fast_name = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=1,
    max_size=15,
)

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

_registry_id = st.builds(
    lambda n: f"NACC-{n:06d}",
    st.integers(min_value=1, max_value=999999),
)


@st.composite
def active_user_entry_strategy(draw):
    """Generate random CenterUserEntry objects representing active users."""
    first_name = draw(_fast_name)
    last_name = draw(_fast_name)
    email = draw(_fast_email)
    auth_email = draw(_fast_email)
    adcid = draw(st.integers(min_value=1, max_value=999))

    return CenterUserEntry(
        name=PersonName(first_name=first_name, last_name=last_name),
        email=email,
        auth_email=auth_email,
        active=True,
        approved=True,
        org_name="Test Center",
        adcid=adcid,
        authorizations=Authorizations(),
        study_authorizations=[],
    )


@st.composite
def suspended_person_strategy(draw):
    """Generate a mock suspended RegistryPerson with a random registry ID."""
    reg_id = draw(_registry_id)
    person = Mock(spec=RegistryPerson)
    person.is_suspended.return_value = True
    person.is_claimed.return_value = False
    person.registry_id.return_value = reg_id
    person.creation_date = None
    return person


@given(
    entry=active_user_entry_strategy(),
    suspended_persons=st.lists(suspended_person_strategy(), min_size=1, max_size=3),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_active_process_re_enables_suspended_instead_of_creating_duplicates(
    entry: CenterUserEntry,
    suspended_persons: list,
):
    """Property 3: Active process re-enables suspended users instead of
    creating duplicates.

    **Feature: disable-inactive-comanage-users, Property 3: Active process
    re-enables suspended users instead of creating duplicates**
    **Validates: Requirements 4.1, 4.2**

    For any active user entry whose email matches suspended RegistryPerson
    objects, the ActiveUserProcess calls re_enable for each and never calls
    add.
    """
    # Arrange
    mock_env = Mock(spec=UserProcessEnvironment)
    mock_env.user_registry = Mock()
    mock_env.notification_client = Mock()
    mock_env.find_user = Mock(return_value=None)
    mock_env.get_from_registry = Mock(
        side_effect=lambda email: mock_env.user_registry.get(email=email)
    )
    mock_env.user_registry.get_by_parent_domain = Mock(return_value=[])
    mock_env.user_registry.get_by_name = Mock(return_value=[])

    # Registry lookup returns the suspended persons
    mock_env.user_registry.get.return_value = suspended_persons

    collector = UserEventCollector()
    process = ActiveUserProcess(mock_env, collector)

    # Act
    process.visit(entry)

    # Assert: re_enable called for each suspended person with a registry ID
    expected_ids = [p.registry_id() for p in suspended_persons if p.registry_id()]
    assert mock_env.user_registry.re_enable.call_count == len(expected_ids)
    for reg_id in expected_ids:
        mock_env.user_registry.re_enable.assert_any_call(reg_id)

    # Assert: add is never called (no duplicate creation)
    mock_env.user_registry.add.assert_not_called()
