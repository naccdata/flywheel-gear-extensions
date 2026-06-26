# Spec Prompt: Disable Inactive Users in User Management Gear

## Goal

Update the user management gear so that users marked inactive in the NACC directory are disabled in Flywheel rather than silently ignored.

## Background

The user management gear processes a directory of user entries. Each entry has an `active` flag. Currently, `InactiveUserProcess` simply logs "ignoring inactive entry" and does nothing. The desired behavior is to disable these users in Flywheel and clean up their associated records.

## Current State

- `InactiveUserProcess` in `common/src/python/users/user_processes.py` is a no-op — it logs and skips inactive entries
- `FlywheelProxy` in `common/src/python/flywheel_adaptor/flywheel_proxy.py` has `find_user(user_id)` and `set_user_email()` but no method to disable a user or find users by email
- `UserRegistry` in `common/src/python/users/user_registry.py` has no delete/removal capability
- The mypy stub for `modify_user` in `mypy-stubs/src/python/flywheel/client.pyi` currently only accepts `Dict[str, str]` — it needs to also accept `bool` values and the `clear_permissions` parameter
- `InactiveUserProcess` currently receives only a `UserEventCollector` — it has no access to `UserProcessEnvironment` and therefore no access to the Flywheel proxy or registry

## Flywheel SDK Details

The Flywheel SDK `Client.modify_user` method supports disabling a user:

```python
client.modify_user(user_id, {"disabled": True}, clear_permissions=True)
```

This disables the user account and removes all project/group permissions.

## Requirements

### Disable user in Flywheel

When a user entry is marked inactive:
1. Look up Flywheel users matching the entry's email address
2. Disable each matching Flywheel user via `modify_user` with `{"disabled": True}` and `clear_permissions=True`
3. Log each disable action

### Provide access to environment

`InactiveUserProcess` needs access to `UserProcessEnvironment` (or at minimum the `FlywheelProxy`) to perform the disable operation. Currently it only receives a `UserEventCollector`.

### Update FlywheelProxy

Add methods to `FlywheelProxy`:
- `find_user_by_email(email: str)` — returns list of users matching the email
- `disable_user(user: flywheel.User)` — calls `modify_user(user.id, {"disabled": True}, clear_permissions=True)`

Both methods should respect the existing `dry_run` flag on the proxy.

### Update type stub

Update the `modify_user` signature in `mypy-stubs/src/python/flywheel/client.pyi` to:

```python
def modify_user(self, user_id: str, body: Dict[str, str | bool], clear_permissions: Optional[bool] = False) -> None:
```

### Event collection

Disable events should be captured through the existing `UserEventCollector` pattern so they appear in the gear's output reporting.

## Out of Scope (for now)

- **Registry cleanup**: Deleting or deactivating records in the COManage registry. The previous branch had this commented out with a TODO. Defer until the COManage API behavior is confirmed.
- **REDCap removal**: Removing users from REDCap projects. The previous branch had an empty stub for this. Defer to a separate effort.

## Key Files

- #[[file:common/src/python/users/user_processes.py]] — `InactiveUserProcess` class
- #[[file:common/src/python/flywheel_adaptor/flywheel_proxy.py]] — `FlywheelProxy` class
- #[[file:common/src/python/users/user_process_environment.py]] — `UserProcessEnvironment`
- #[[file:common/src/python/users/user_entry.py]] — `UserEntry` model
- #[[file:mypy-stubs/src/python/flywheel/client.pyi]] — type stub for Flywheel client
- #[[file:gear/user_management/src/python/user_app/run.py]] — gear entry point
- #[[file:gear/user_management/src/python/user_app/main.py]] — gear main logic
