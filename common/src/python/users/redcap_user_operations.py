"""Helper functions for REDCap user operations."""

from typing import Optional

from redcap_api.redcap_project import REDCapProject


def unassign_user_role(redcap_project: REDCapProject, username: str) -> int:
    """Unassign a user from their role in a REDCap project.

    Calls assign_user_role with an empty role string, which removes the
    user's role-based permissions without deleting the user record.

    Args:
        redcap_project: The REDCap project instance
        username: The REDCap username (typically the auth_email)

    Returns:
        Number of user-role assignments updated

    Raises:
        REDCapConnectionError: If the underlying API call fails
    """
    return redcap_project.assign_user_role(username, "")


def user_has_role_assignment(
    redcap_project: REDCapProject, username: str, include_empty: Optional[bool] = True
) -> bool:
    """Check whether a user has a role assignment in a REDCap project.

    Queries the project's user-role mappings and checks whether the
    given username appears in any assignment.

    Args:
        redcap_project: The REDCap project instance
        username: The REDCap username to look up
        include_empty (optional): Whether to include users with empty role assignments.
                                  Default True

    Returns:
        True if the username has a role assignment, or empty role (include_empty=True).
        False otherwise

    Raises:
        REDCapConnectionError: If the underlying API call fails
    """
    assignments = redcap_project.export_user_role_assignments()
    if include_empty:
        return any(assignment["username"] == username for assignment in assignments)

    return any(
        assignment["username"] == username and assignment.get("unique_role_name")
        for assignment in assignments
    )


def delete_user(redcap_project: REDCapProject, username: str) -> int:
    """Remove a user from a REDCap project.

    Args:
        redcap_project: The REDCap project instance
        username: The REDCap username (typically the auth_email)

    Returns:
        Number of users removed

    Raises:
        REDCapConnectionError: If the underlying API call fails
    """
    return redcap_project.delete_user(username=username)
