"""Tests for REDCap user operations helper functions."""

from unittest.mock import Mock

import pytest
from redcap_api.redcap_connection import REDCapConnectionError
from redcap_api.redcap_project import REDCapProject
from users.redcap_user_operations import (
    delete_user,
    unassign_user_role,
    user_has_role_assignment,
)


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

    def test_delete_user(self):
        """Test delete_user calls delete_user with the username."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.delete_user.return_value = 1

        delete_user(mock_project, "user@example.com")

        mock_project.delete_user.assert_called_once_with("user@example.com")


class TestUserHasRoleAssignment:
    """Tests for user_has_role_assignment helper function."""

    def test_returns_true_when_username_in_mapping_list(self):
        """When the username appears in the role assignment list, returns
        True."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.return_value = [
            {"username": "alice@uni.edu", "unique_role_name": "U-role1"},
            {"username": "bob@uni.edu", "unique_role_name": "U-role2"},
        ]

        result = user_has_role_assignment(mock_project, "alice@uni.edu")

        assert result is True

    def test_returns_false_when_username_not_in_mapping_list(self):
        """When the username does not appear in the role assignment list,
        returns False."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.return_value = [
            {"username": "alice@uni.edu", "unique_role_name": "U-role1"},
            {"username": "bob@uni.edu", "unique_role_name": "U-role2"},
        ]

        result = user_has_role_assignment(mock_project, "carol@uni.edu")

        assert result is False

    def test_returns_false_when_mapping_list_is_empty(self):
        """When the role assignment list is empty, returns False."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.return_value = []

        result = user_has_role_assignment(mock_project, "user@example.com")

        assert result is False

    def test_returns_false_when_user_does_not_exist(self):
        """When the username does not appear in the role assignment list,
        returns False."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.return_value = [
            {"username": "alice@uni.edu", "unique_role_name": "U-role1"},
            {"username": "bob@uni.edu", "unique_role_name": "U-role2"},
        ]

        result = user_has_role_assignment(mock_project, "carol@uni.edu")

        assert result is False

    def test_include_empty_true(self):
        """Returns True if username appears in the role assignment list with an
        empty role."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.return_value = [
            {"username": "alice@uni.edu", "unique_role_name": "U-role1"},
            {"username": "bob@uni.edu", "unique_role_name": "U-role2"},
            {"username": "carol@uni.edu", "unique_role_name": ""},
        ]

        result = user_has_role_assignment(
            mock_project, "carol@uni.edu", include_empty=False
        )

        assert result is True

    def test_include_empty_false(self):
        """Returns False if username appears in the role assignment list with
        an empty role."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.return_value = [
            {"username": "alice@uni.edu", "unique_role_name": "U-role1"},
            {"username": "bob@uni.edu", "unique_role_name": "U-role2"},
            {"username": "carol@uni.edu", "unique_role_name": ""},
        ]

        result = user_has_role_assignment(
            mock_project, "carol@uni.edu", include_empty=False
        )

        assert result is False

    def test_propagates_redcap_connection_error(self):
        """REDCapConnectionError from export_user_role_assignments propagates
        to the caller."""
        mock_project = Mock(spec=REDCapProject)
        mock_project.export_user_role_assignments.side_effect = REDCapConnectionError(
            "Connection failed"
        )

        with pytest.raises(REDCapConnectionError):
            user_has_role_assignment(mock_project, "user@example.com")
