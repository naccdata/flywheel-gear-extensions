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
    email = draw(st.emails())
    user = Mock(spec=User)
    user.id = user_id
    user.email = email
    return user


def _build_proxy(mock_client: Mock, dry_run: bool) -> FlywheelProxy:
    """Build a FlywheelProxy with a mock client and dry_run setting."""
    proxy = FlywheelProxy.__new__(FlywheelProxy)
    # Access the name-mangled attributes directly
    object.__setattr__(proxy, "_FlywheelProxy__fw", mock_client)
    object.__setattr__(proxy, "_FlywheelProxy__dry_run", dry_run)
    return proxy


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
