"""Property tests for InactiveUserProcess.

Tests Property 1 from the disable-inactive-users design document.
"""

from unittest.mock import Mock, call

from flywheel.models.user import User
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from hypothesis import given, settings
from hypothesis import strategies as st
from users.event_models import UserEventCollector
from users.user_entry import PersonName, UserEntry
from users.user_process_environment import UserProcessEnvironment
from users.user_processes import InactiveUserProcess


@st.composite
def inactive_user_entry_strategy(draw):
    """Generate inactive UserEntry objects."""
    first_name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        )
    )
    last_name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        )
    )
    email = draw(st.emails())
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
    for _ in range(count):
        user_id = draw(
            st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            )
        )
        email = draw(st.emails())
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
