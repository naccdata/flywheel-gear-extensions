"""Tests for REDCap user operations helper functions."""

from unittest.mock import Mock

import pytest
from redcap_api.redcap_connection import REDCapConnectionError
from redcap_api.redcap_project import REDCapProject
from users.redcap_user_operations import unassign_user_role


class TestUnassignUserRole:
    """Tests for unassign_user_role helper function."""

    def test_calls_assign_user_role_with_empty_role(self):
        """Test that unassign_user_role calls assign_user_role with the
        username and an empty string for the role."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.assign_user_role.return_value = 1

        unassign_user_role(mock_project, "user@example.com")

        mock_project.assign_user_role.assert_called_once_with("user@example.com", "")

    def test_returns_count_from_assign_user_role(self):
        """Test that unassign_user_role returns the count from
        assign_user_role."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.assign_user_role.return_value = 3

        result = unassign_user_role(mock_project, "user@example.com")

        assert result == 3

    def test_propagates_redcap_connection_error(self):
        """Test that REDCapConnectionError from assign_user_role propagates to
        the caller."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.assign_user_role.side_effect = REDCapConnectionError(
            "Connection failed"
        )

        with pytest.raises(REDCapConnectionError):
            unassign_user_role(mock_project, "user@example.com")
