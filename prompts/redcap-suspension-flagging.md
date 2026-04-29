# REDCap User Suspension Flagging

> **Status: Shelved (April 2026)**
>
> We decided not to implement this because the `export_users` check would be
> redundant. Every user we unassign a role from will still exist in the project
> afterward — REDCap auto-creates a user record when you assign a role mapping,
> and unassigning the role doesn't remove that record. So `export_users` would
> always return true for users we just unassigned, adding API calls without
> filtering anyone out of the email.
>
> The membership check fix (checking `export_user_role_assignments` before
> calling `unassign_user_role`) already eliminates the main source of noise:
> users who never had a role no longer appear in the notification email.
>
> The `export_users()` method is available in `redcap_api` if we find a use
> for it later — for example, if REDCap adds a suspended/expiration flag to
> the Export Users response that would let us detect users the admin has
> already dealt with.

## Context

The user management gear disables inactive users across three systems: Flywheel, REDCap, and COmanage. The REDCap disable step (`InactiveUserProcess.__disable_in_redcap` in `common/src/python/users/user_processes.py`) currently only unassigns user roles — it calls `assign_user_role(username, "")` to remove the role mapping. However, unassigning a role does not remove the user from the REDCap project. The user record persists with whatever permissions remain, and an admin must manually suspend them in the REDCap UI.

Today, the gear sends an email to support staff listing every user whose role was unassigned, with the message "Please manually suspend these users' REDCap accounts." This email is sent by `__send_redcap_disable_notification` in `gear/user_management/src/python/user_app/run.py`. The problem is that this email only tells admins *which users had roles removed* — it doesn't tell them which REDCap projects the user still exists in after role removal. The admin has to go check each project manually.

## What We Want

After unassigning a user's role from a REDCap project, check whether the user still exists in that project using the REDCap Export Users API (`content: "user"`). If the user is still present, flag them for manual suspension by collecting an event that will be included in the notification email.

The `redcap_api` package (v0.4.0) now has an `export_users()` method on `REDCapProject`:

```python
def export_users(self) -> List[Dict[str, Any]]:
    """Export the list of users for the project.

    Returns the list of users in the project with their privileges.
    Each entry contains at minimum ``username``, ``email``,
    ``firstname``, and ``lastname`` keys, along with privilege flags.

    Returns:
        List of user dicts with privileges

    Raises:
        REDCapConnectionError if the response has an error
    """
```

## Requirements

### Functional

1. After successfully unassigning a user's role from a REDCap project, call `export_users()` on that project and check whether the username still appears in the user list.

2. If the user is still present in the project after role unassignment, collect a new event that indicates the user needs manual suspension. This event should include the username, project title, and PID so the notification email can tell admins exactly where to act.

3. If the user is NOT present in the project after role unassignment (unlikely but possible if they were removed by other means), do not flag them.

4. If `export_users()` fails with a `REDCapConnectionError`, handle it gracefully — log the error, collect an error event, and continue processing. Do not let this failure block the rest of the disable flow.

5. In dry-run mode, skip the `export_users()` check (since no role was actually unassigned, the user's state hasn't changed).

### Event Design

Consider whether to:
- (a) Add a new `EventCategory` (e.g., `REDCAP_USER_NEEDS_SUSPENSION`) to distinguish "role was removed" from "user still exists and needs manual suspension", or
- (b) Reuse `REDCAP_USER_DISABLED` with a different message format that the notification code can parse.

Option (a) is cleaner — it lets the notification email have a separate section for users needing suspension vs. roles that were removed. The existing `__send_redcap_disable_notification` in `run.py` would need to be updated to include the new category.

### Notification Email

Update `__send_redcap_disable_notification` in `gear/user_management/src/python/user_app/run.py` to include the suspension-needed information. The email should clearly distinguish between:
- Role removals that were performed (existing behavior)
- Users that still need manual suspension in specific REDCap projects (new)

### Unchanged Behavior

- The role unassignment logic must remain unchanged — this is additive.
- The existing `REDCAP_USER_DISABLED` success events for role removal must continue to work as before.
- Error handling for role unassignment failures must remain unchanged.
- The membership check (`user_has_role_assignment`) before unassignment must remain unchanged.

## Key Files

- `common/src/python/users/user_processes.py` — `InactiveUserProcess.__unassign_redcap_project` (add `export_users` check after successful unassignment)
- `common/src/python/users/redcap_user_operations.py` — add a helper function (e.g., `user_exists_in_project`) that wraps `export_users()` and checks for the username
- `common/src/python/users/event_models.py` — add new `EventCategory` if going with option (a)
- `gear/user_management/src/python/user_app/run.py` — update `__send_redcap_disable_notification` to include suspension-needed events

## Implementation Notes

- The `export_users()` call returns a list of dicts, each with a `username` key. The check is: does any returned user dict have `username` matching the target username?
- This check should happen only after a successful `unassign_user_role` call — not after dry-run, not after errors, not when the user had no role to begin with.
- The `__unassign_redcap_project` method already has the `redcap_project` object, `username`, `title`, `pid`, and `user_context` in scope at the point where the check would be added.
- Follow the existing error handling pattern: catch `REDCapConnectionError`, log, collect error event, continue.
