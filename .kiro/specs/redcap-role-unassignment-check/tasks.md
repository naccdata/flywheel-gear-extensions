# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Non-Member User Still Gets Unassigned
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases where `export_user_role_assignments()` returns mappings that do NOT include the target username
  - Add a new test class `TestBugConditionExploration` in `common/test/python/user_test/test_inactive_user_process_redcap.py`
  - Mock `export_user_role_assignments()` on the mock REDCap project to return a list of mappings for OTHER users only (e.g., `[{"username": "other@uni.edu", "unique_role_name": "U-role1"}]`)
  - Set up a single center with one REDCap project (PID 100) using existing `_build_center_metadata_with_redcap` and `_setup_center_map_with_centers` helpers
  - Call `process.visit(entry)` on an inactive user entry (e.g., `user@example.com`)
  - Assert that `assign_user_role` is NOT called for that project (bug condition: it IS called on unfixed code)
  - Assert that no success event with category `REDCAP_USER_DISABLED` is emitted (bug condition: one IS emitted on unfixed code)
  - Also test the multi-project mixed membership case: set up 3 projects where user is a member of PID 100 only (mapping includes username), not PID 200 or PID 300. Assert `assign_user_role` is called exactly once (for PID 100 only)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct — it proves the bug exists because `assign_user_role` is called unconditionally)
  - Document counterexamples found: `assign_user_role` called with `("user@example.com", "")` even though `export_user_role_assignments()` shows user has no role
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Member User Unassignment and Existing Behaviors Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Add a new test class `TestPreservationProperties` in `common/test/python/user_test/test_inactive_user_process_redcap.py`
  - **Observe on UNFIXED code first**, then write tests capturing observed behavior:
  - Observe: When user IS a member (mapping includes username), `assign_user_role(username, "")` is called and a success event with `REDCAP_USER_DISABLED` category is emitted — verify this on unfixed code
  - Observe: When in dry-run mode with a member user, `assign_user_role` is NOT called but a dry-run success event IS emitted — verify this on unfixed code
  - Observe: When `assign_user_role` raises `REDCapConnectionError` for a member user, an error event with `REDCAP_USER_DISABLED` category is emitted and processing continues — verify this on unfixed code
  - Observe: When `get_redcap_project` returns `None` (credentials unavailable), the project is skipped with an error event — verify this on unfixed code
  - Mock `export_user_role_assignments()` to return mappings that INCLUDE the target username (e.g., `[{"username": "user@example.com", "unique_role_name": "U-role1"}]`) for member-user tests
  - Write property-based style tests (parameterized across multiple username/mapping combinations) asserting the observed behaviors are preserved
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for REDCap role unassignment without membership check

  - [x] 3.1 Add `user_has_role_assignment` helper to `redcap_user_operations.py`
    - Add a new function `user_has_role_assignment(redcap_project: REDCapProject, username: str) -> bool` in `common/src/python/users/redcap_user_operations.py`
    - Call `redcap_project.export_user_role_assignments()` to get the list of user-role mappings
    - Return `True` if any mapping has `assignment["username"] == username`, `False` otherwise
    - Let `REDCapConnectionError` propagate to the caller (do not catch it)
    - Add unit tests in `common/test/python/user_test/test_redcap_user_operations.py`:
      - Test returns `True` when username is in the mapping list
      - Test returns `False` when username is not in the mapping list
      - Test returns `False` when the mapping list is empty
      - Test propagates `REDCapConnectionError` from `export_user_role_assignments()`
    - _Bug_Condition: isBugCondition(input) where user has no role assignment but unassign is called_
    - _Expected_Behavior: user_has_role_assignment returns False for non-members, True for members_
    - _Preservation: Existing unassign_user_role function unchanged_
    - _Requirements: 2.4_

  - [x] 3.2 Update `__unassign_redcap_project` in `user_processes.py` to check membership
    - Import `user_has_role_assignment` from `users.redcap_user_operations` (add to existing import line)
    - After obtaining `redcap_project` and its `title`, but BEFORE the dry-run check, add a membership check:
      - Call `user_has_role_assignment(redcap_project, username)` wrapped in a try/except for `REDCapConnectionError`
      - If user is NOT a member: log an info message (`"User %s has no role assignment in REDCap project %s (PID %s), skipping"`) and return early — no API call, no event
      - If `REDCapConnectionError` is raised from the membership check: log an error, emit an error event with `EventCategory.REDCAP_USER_DISABLED`, and return (skip the project gracefully)
    - If user IS a member: proceed with existing logic (dry-run check, unassign call, event collection) unchanged
    - _Bug_Condition: isBugCondition(input) where NOT user_in_project AND unassign_user_role_is_called_
    - _Expected_Behavior: When not a member, skip unassignment and emit no success event; when a member, proceed as before_
    - _Preservation: All existing behavior for member users, dry-run, error handling, credential unavailability unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Non-Member User Skipped Correctly
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (no `assign_user_role` call, no success event for non-members)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Member User Unassignment and Existing Behaviors Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite for the affected test files:
    - `common/test/python/user_test/test_inactive_user_process_redcap.py`
    - `common/test/python/user_test/test_redcap_user_operations.py`
  - Ensure ALL tests pass (both new and existing)
  - Ask the user if questions arise
