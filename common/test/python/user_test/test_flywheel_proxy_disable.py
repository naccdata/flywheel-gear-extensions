"""Property tests for FlywheelProxy disable-related methods.

Tests Properties 3 and 4 from the disable-inactive-users design
document.
"""

from unittest.mock import Mock

import pytest
from flywheel.models.user import User
from flywheel.rest import ApiException
from flywheel_adaptor.flywheel_proxy import FlywheelError, FlywheelProxy
from hypothesis import given, settings
from hypothesis import strategies as st

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


@st.composite
def mock_user_strategy(draw):
    """Generate mock Flywheel User objects with random IDs and emails."""
    user_id = draw(
        st.text(
            min_size=1,
            max_size=30,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        )
    )
    email = draw(_fast_email)
    user = Mock(spec=User)
    user.id = user_id
    user.email = email
    return user


def _build_proxy(mock_client: Mock, dry_run: bool) -> FlywheelProxy:
    """Build a FlywheelProxy with a mock client and dry_run setting."""
    return FlywheelProxy(client=mock_client, dry_run=dry_run)


class TestDisableUserDryRunProperty:
    """Property 3: Disable user calls SDK if and only if not in dry-run mode.

    Feature: disable-inactive-users, Property 3: Disable user calls SDK
    if and only if not in dry-run mode.
    """

    @given(user=mock_user_strategy(), dry_run=st.booleans())
    @settings(max_examples=100)
    def test_disable_user_calls_sdk_iff_not_dry_run(
        self, user: Mock, dry_run: bool
    ) -> None:
        """For any User and any dry-run setting, modify_user is called exactly
        when dry_run is False."""
        mock_client = Mock()
        proxy = _build_proxy(mock_client, dry_run)

        proxy.disable_user(user)

        if dry_run:
            mock_client.modify_user.assert_not_called()
        else:
            mock_client.modify_user.assert_called_once_with(
                user.id, {"disabled": True}, clear_permissions=True
            )


class TestDisableUserErrorWrappingProperty:
    """Property 4: Disable user wraps SDK errors in FlywheelError.

    Feature: disable-inactive-users, Property 4: Disable user wraps SDK
    errors in FlywheelError.
    """

    @given(user=mock_user_strategy())
    @settings(max_examples=100)
    def test_disable_user_wraps_api_exception_in_flywheel_error(
        self, user: Mock
    ) -> None:
        """For any User, if modify_user raises ApiException, then disable_user
        raises FlywheelError with a descriptive message."""
        mock_client = Mock()
        mock_client.modify_user.side_effect = ApiException(
            status=500, reason="Internal Server Error"
        )
        proxy = _build_proxy(mock_client, dry_run=False)

        with pytest.raises(FlywheelError, match=f"Failed to disable user {user.id}"):
            proxy.disable_user(user)
