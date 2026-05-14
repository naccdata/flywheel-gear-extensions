# REDCap Role Unassignment Check Bugfix Design

## Overview

The `InactiveUserProcess.__unassign_redcap_project` method currently calls `unassign_user_role` for every REDCap project across all centers, regardless of whether the user actually has a role assignment in that project. This produces unnecessary REDCap API calls and misleading success events.

The fix adds a membership check before attempting role unassignment. A new `export_user_role_assignments()` method on `REDCapProject` (in the external `redcap_api` package) queries the REDCap `userRoleMapping` export API. A new helper function `user_has_role_assignment()` in `redcap_user_operations.py` uses this export to check whether a username appears in the project's user-role mappings. The `__unassign_redcap_project` method is then updated to skip unassignment (and skip event collection) when the user is not found.

## Glossary

- **Bug_Condition (C)**: The user does NOT have a role assignment in the REDCap project, yet `unassign_user_role` is called and a success event is emitted
- **Property (P)**: When the user has no role assignment, the system skips unassignment and emits no success event; when the user does have a role assignment, the system unassigns and emits a success event as before
- **Preservation**: All existing behavior for users who DO have role assignments, dry-run mode, credential unavailability, error handling, and center iteration must remain unchanged
- **`__unassign_redcap_project`**: The private method in `InactiveUserProcess` (in `user_processes.py`) that attempts to unassign a user's role from a single REDCap project
- **`unassign_user_role`**: The helper function in `redcap_user_operations.py` that calls `REDCapProject.assign_user_role(username, "")` to remove a user's role
- **`export_user_role_assignments`**: A new method to be added to `REDCapProject` that exports user-role mappings via the REDCap API (`content: "userRoleMapping"`, `action: "export"`)
- **`user_has_role_assignment`**: A new helper function in `redcap_user_operations.py` that checks whether a username appears in a project's user-role mapping export
- **User-role mapping**: A REDCap record associating a username with a unique role name in a project

## Bug Details

### Bug Condition

The bug manifests when `__unassign_redcap_project` is called for a REDCap project where the user has no role assignment. The method unconditionally calls `unassign_user_role` and emits a success event, even though the user was never assigned a role in that project.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {redcap_project: REDCapProject, username: str}
  OUTPUT: boolean

  role_assignments := redcap_project.export_user_role_assignments()
  user_in_project := ANY assignment IN role_assignments
                     WHERE assignment["username"] == username

  RETURN NOT user_in_project
         AND unassign_user_role_is_called(redcap_project, username)
END FUNCTION
```

### Examples

- **User not in project**: User `alice@uni.edu` is being disabled. REDCap project PID 100 has role assignments for `bob@uni.edu` and `carol@uni.edu` only. Current behavior: `unassign_user_role` is called for `alice@uni.edu` in PID 100 and a success event is emitted. Expected: skip PID 100 entirely, no API call, no event.
- **User in project**: User `alice@uni.edu` is being disabled. REDCap project PID 200 has a role assignment for `alice@uni.edu`. Current behavior: `unassign_user_role` is called. Expected: same — `unassign_user_role` is called and a success event is emitted.
- **User not in any project across multiple centers**: User `dave@uni.edu` is being disabled across 3 centers with 5 REDCap projects total. `dave@uni.edu` has no role in any of them. Current behavior: 5 unnecessary API calls and 5 misleading success events. Expected: 0 API calls, 0 events.
- **User in some projects but not others**: User `eve@uni.edu` is being disabled. She has a role in PID 100 and PID 300 but not in PID 200. Current behavior: 3 API calls, 3 success events. Expected: 2 API calls (PID 100 and 300), 2 success events, PID 200 skipped.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- When a user DOES have a role assignment in a REDCap project, `unassign_user_role` must continue to be called and a success event emitted with the project title and PID
- When REDCap project credentials are unavailable (`get_redcap_project` returns `None`), the project must continue to be skipped with an error event
- When in dry-run mode, the actual `unassign_user_role` call must continue to be skipped and a dry-run success event emitted
- When `unassign_user_role` raises `REDCapConnectionError`, the error must continue to be caught, an error event emitted, and processing must continue to the next project
- When a center group cannot be retrieved, that center must continue to be skipped and remaining centers processed
- Auth email resolution priority (entry.auth_email > COmanage auth_email > directory email) must remain unchanged
- Step independence (Flywheel disable, COmanage lookup, REDCap role removal, COmanage suspend) must remain unchanged
- Event `UserContext` must continue to contain the user's email, name, and center ID

**Scope:**
All inputs where the user DOES have a role assignment in the REDCap project should be completely unaffected by this fix. The only behavioral change is for inputs where the user does NOT have a role assignment — those now skip the unassignment call and event collection.

## Hypothesized Root Cause

Based on the bug description, the root cause is straightforward:

1. **Missing membership check**: The `__unassign_redcap_project` method does not check whether the user has a role assignment in the project before calling `unassign_user_role`. It unconditionally proceeds with the API call for every project discovered by the `REDCapDisableVisitor`.

2. **No user-role mapping export capability**: The `REDCapProject` class in the `redcap_api` package does not currently have a method to export user-role mappings. It has `export_user_roles()` (which exports role definitions, not user-role assignments) and `assign_user_role()` (which imports/updates assignments), but no export for the `userRoleMapping` content type. This means there was no convenient way to check membership when the original code was written.

3. **Unconditional success event emission**: The success event is emitted immediately after a successful `unassign_user_role` call, without verifying that the user actually had a role to unassign. The REDCap API does not error when unassigning a role from a user who has no role — it simply returns a count, making the bug silent.

## Correctness Properties

Property 1: Bug Condition - Skip Unassignment for Non-Member Users

_For any_ input where the user does NOT have a role assignment in the REDCap project (isBugCondition returns true), the fixed `__unassign_redcap_project` method SHALL NOT call `unassign_user_role` and SHALL NOT emit a success event for that project.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Unassignment Behavior for Member Users

_For any_ input where the user DOES have a role assignment in the REDCap project (isBugCondition returns false), the fixed `__unassign_redcap_project` method SHALL produce the same result as the original method — calling `unassign_user_role` and emitting a success event with the project title and PID, preserving all existing behavior for users who are members of the project.

**Validates: Requirements 2.3, 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `redcap_api` package — `redcap_api/redcap_project.py` (external)

**Method**: New `export_user_role_assignments`

**Specific Changes**:
1. **Add `export_user_role_assignments()` method to `REDCapProject`**: This method calls the REDCap API with `content: "userRoleMapping"` and `action: "export"` to retrieve the list of user-role assignments. Returns `List[Dict[str, Any]]` where each dict has `username` and `unique_role_name` keys. Raises `REDCapConnectionError` on failure.

---

**File**: `common/src/python/users/redcap_user_operations.py`

**Function**: New `user_has_role_assignment`

**Specific Changes**:
2. **Add `user_has_role_assignment(redcap_project, username)` helper function**: Calls `redcap_project.export_user_role_assignments()` and checks whether any returned mapping has a `username` field matching the given username. Returns `bool`. Lets `REDCapConnectionError` propagate to the caller.

---

**File**: `common/src/python/users/user_processes.py`

**Method**: `InactiveUserProcess.__unassign_redcap_project`

**Specific Changes**:
3. **Add membership check before unassignment**: After obtaining the `redcap_project` and its title, but before the dry-run check, call `user_has_role_assignment(redcap_project, username)`. If the user is not a member, log an info message and return early without calling `unassign_user_role` and without emitting any event.

4. **Handle `REDCapConnectionError` from membership check**: If `export_user_role_assignments()` fails, catch the `REDCapConnectionError`, log an error, emit an error event with `REDCAP_USER_DISABLED` category, and return (skip the project gracefully).

5. **Import `user_has_role_assignment`**: Add the import of the new helper function from `users.redcap_user_operations`.

## External Dependency: `redcap_api` Package Change

The `redcap_api` package is an external dependency (not in this repository). The new `export_user_role_assignments()` method must be added there first, before the changes in this repo can be implemented.

### Prompt for `redcap_api` Repository

Use the following prompt in the `redcap_api` workspace to implement the required change:

---

**Add `export_user_role_assignments()` method to `REDCapProject`**

The `REDCapProject` class needs a new method to export user-role mappings from a project. This is the counterpart to the existing `assign_user_role()` method (which imports/updates mappings). The new method exports the current user-role assignments so callers can check which users have roles before modifying them.

**Method signature:**

```python
def export_user_role_assignments(self) -> List[Dict[str, Any]]:
```

**Implementation pattern** — follow the same pattern as `export_user_roles()`:

```python
def export_user_role_assignments(self) -> List[Dict[str, Any]]:
    """Export user-role assignments for the project.

    Returns the mapping of users to roles in the project. Each entry
    contains a ``username`` and ``unique_role_name`` key.

    Returns:
        List of user-role assignment dicts

    Raises:
        REDCapConnectionError if the response has an error
    """
    message = "exporting user-role assignments"
    data = {"content": "userRoleMapping", "action": "export"}

    return self.__redcap_con.request_json_value(data=data, message=message)
```

**Context:**
- The REDCap API's `userRoleMapping` content type with `action: "export"` returns a JSON array of objects, each with `username` and `unique_role_name` keys
- The existing `assign_user_role()` method already uses `content: "userRoleMapping"` with `action: "import"` — this is the export counterpart
- The existing `export_user_roles()` method uses `content: "userRole"` which exports role definitions (not user-role assignments) — this is different
- Follow the same error handling pattern: let `request_json_value` raise `REDCapConnectionError` on failure

**Tests to add:**
- Test that the method sends the correct data payload (`content: "userRoleMapping"`, `action: "export"`)
- Test that it returns the parsed JSON response
- Test that `REDCapConnectionError` propagates on failure

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that mock `export_user_role_assignments()` to return mappings that do NOT include the target username, then verify that `unassign_user_role` is still called (demonstrating the bug on unfixed code). Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Non-member unassignment test**: Mock a REDCap project where `export_user_role_assignments()` returns mappings for other users only. Call `visit()` on an inactive user entry. Assert that `assign_user_role` is NOT called for that project (will fail on unfixed code because it IS called).
2. **Non-member event test**: Same setup as above. Assert that no success event is emitted for the project (will fail on unfixed code because a success event IS emitted).
3. **Multiple projects mixed membership test**: Set up 3 projects — user is a member of 1, not a member of 2. Assert that `assign_user_role` is called only for the 1 project where the user is a member (will fail on unfixed code because all 3 are called).
4. **No membership in any project test**: User has no role in any of 3 projects across 2 centers. Assert zero `assign_user_role` calls (will fail on unfixed code).

**Expected Counterexamples**:
- `assign_user_role` is called even when the user has no role assignment in the project
- Success events are emitted for projects where the user was never a member
- Possible cause: no membership check exists in `__unassign_redcap_project`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := __unassign_redcap_project_fixed(input)
  ASSERT unassign_user_role NOT called
  ASSERT no success event emitted
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT __unassign_redcap_project_original(input) = __unassign_redcap_project_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss (e.g., username case sensitivity, empty role mappings)
- It provides strong guarantees that behavior is unchanged for all users who ARE members

**Test Plan**: Observe behavior on UNFIXED code first for users who DO have role assignments, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Member unassignment preservation**: Observe that `unassign_user_role` is called for users who have role assignments on unfixed code, then write test to verify this continues after fix
2. **Dry-run preservation**: Observe that dry-run mode skips the API call and emits a dry-run event on unfixed code, then write test to verify this continues after fix
3. **Error handling preservation**: Observe that `REDCapConnectionError` from `unassign_user_role` is caught and an error event emitted on unfixed code, then write test to verify this continues after fix
4. **Credential unavailability preservation**: Observe that projects with unavailable credentials are skipped on unfixed code, then write test to verify this continues after fix

### Unit Tests

- Test `export_user_role_assignments()` on `REDCapProject` calls the correct API endpoint (`content: "userRoleMapping"`, `action: "export"`)
- Test `user_has_role_assignment()` returns `True` when username is in the mapping list
- Test `user_has_role_assignment()` returns `False` when username is not in the mapping list
- Test `user_has_role_assignment()` returns `False` when the mapping list is empty
- Test `user_has_role_assignment()` propagates `REDCapConnectionError`
- Test `__unassign_redcap_project` skips unassignment when user is not a member
- Test `__unassign_redcap_project` proceeds with unassignment when user is a member
- Test `__unassign_redcap_project` handles `REDCapConnectionError` from membership check gracefully
- Test dry-run mode still checks membership (or skips check — design decision to be confirmed)

### Property-Based Tests

- Generate random sets of usernames and role mappings, verify `user_has_role_assignment` correctly identifies membership for any username
- Generate random project configurations (user in some projects, not in others), verify that `unassign_user_role` is called only for projects where the user has a role assignment
- Generate random inputs where the user IS a member, verify the fixed code produces the same events and API calls as the original code

### Integration Tests

- Test full `visit()` flow with a mix of projects where the user is and is not a member, verifying correct API calls and events
- Test that the membership check failure (REDCapConnectionError) does not block processing of subsequent projects
- Test that step independence is maintained — membership check failure in REDCap step does not affect Flywheel or COmanage steps
