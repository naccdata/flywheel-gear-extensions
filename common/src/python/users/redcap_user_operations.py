"""Helper functions for REDCap user operations."""

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


def user_has_role_assignment(redcap_project: REDCapProject, username: str) -> bool:
    """Check whether a user has a role assignment in a REDCap project.

    Queries the project's user-role mappings and checks whether the
    given username appears in any assignment.

    Args:
        redcap_project: The REDCap project instance
        username: The REDCap username to look up

    Returns:
        True if the username has a role assignment, False otherwise

    Raises:
        REDCapConnectionError: If the underlying API call fails
    """
    assignments = redcap_project.export_user_role_assignments()
    return any(assignment["username"] == username for assignment in assignments)
