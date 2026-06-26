# Implementation Plan: Disable Inactive Users

## Overview

Update the user management gear so that users marked inactive in the NACC directory are disabled in Flywheel. The implementation adds email-based user lookup and disable methods to `FlywheelProxy`, updates `InactiveUserProcess` to use the environment for disabling users, adds a new `EventCategory` member, updates the type stub for `modify_user`, and wires the environment through `UserProcess`.

## Tasks

- [x] 1. Update Flywheel Client type stub and add EventCategory member
  - [x] 1.1 Update `modify_user` signature in `mypy-stubs/src/python/flywheel/client.pyi`
    - Change `body` parameter type from `Dict[str, str]` to `Dict[str, str | bool]`
    - Add `clear_permissions: bool = False` parameter
    - _Requirements: 5.1, 5.2_
  - [x] 1.2 Add `USER_DISABLED` member to `EventCategory` in `common/src/python/users/event_models.py`
    - Add `USER_DISABLED = "User Disabled"` to the `EventCategory` enum
    - _Requirements: 6.2_

- [x] 2. Add `find_user_by_email` and `disable_user` methods to FlywheelProxy
  - [x] 2.1 Implement `find_user_by_email` in `common/src/python/flywheel_adaptor/flywheel_proxy.py`
    - Add method `find_user_by_email(self, email: str) -> List[flywheel.User]`
    - Use `self.__fw.users.find(f"email={email}")` to look up users
    - Execute lookup regardless of `dry_run` mode (read-only operation)
    - Raise `FlywheelError` if `ApiException` occurs
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 2.2 Implement `disable_user` in `common/src/python/flywheel_adaptor/flywheel_proxy.py`
    - Add method `disable_user(self, user: flywheel.User) -> None`
    - In non-dry-run mode: call `self.__fw.modify_user(user.id, {"disabled": True}, clear_permissions=True)`
    - In dry-run mode: log the intended action and return without calling the API
    - Wrap `ApiException` in `FlywheelError` with a descriptive message including user ID
    - _Requirements: 4.1, 4.2, 4.3_
  - [ ]* 2.3 Write property test for `find_user_by_email` (Property 2: Email lookup returns matches regardless of dry-run mode)
    - **Property 2: Email lookup returns matches regardless of dry-run mode**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Create `common/test/python/user_test/test_flywheel_proxy_disable.py`
    - Use Hypothesis to generate random email strings and dry-run settings
    - Mock the Flywheel `Client.users.find` method
    - Verify the lookup result is returned unmodified for both dry_run=True and dry_run=False
  - [x] 2.4 Write property test for `disable_user` dry-run behavior (Property 3: Disable user calls SDK if and only if not in dry-run mode)
    - **Property 3: Disable user calls SDK if and only if not in dry-run mode**
    - **Validates: Requirements 4.1, 4.2**
    - Add to `common/test/python/user_test/test_flywheel_proxy_disable.py`
    - Use Hypothesis to generate mock User objects and dry-run settings
    - Verify `modify_user` is called exactly when `dry_run=False` and not called when `dry_run=True`
  - [x] 2.5 Write property test for `disable_user` error wrapping (Property 4: Disable user wraps SDK errors in FlywheelError)
    - **Property 4: Disable user wraps SDK errors in FlywheelError**
    - **Validates: Requirements 4.3**
    - Add to `common/test/python/user_test/test_flywheel_proxy_disable.py`
    - Use Hypothesis to generate mock User objects
    - Configure mock `modify_user` to raise `ApiException`
    - Verify `FlywheelError` is raised with a descriptive message

- [x] 3. Update `InactiveUserProcess` to disable matching Flywheel users
  - [x] 3.1 Update `InactiveUserProcess.__init__` to accept `UserProcessEnvironment`
    - Add `environment: UserProcessEnvironment` parameter before `collector`
    - Store environment as `self.__env`
    - _Requirements: 2.1, 2.2_
  - [x] 3.2 Implement disable logic in `InactiveUserProcess.visit`
    - Preserve existing log message for the inactive entry (Req 7.1)
    - Call `self.__env.proxy.find_user_by_email(entry.email)` to look up matching users
    - If no matches: log that no matching users were found and return
    - For each match: call `self.__env.proxy.disable_user(user)`, log the disable action with user ID and email
    - On successful disable: collect a success event with category `USER_DISABLED` and `UserContext` containing email, name, and center_id
    - On `FlywheelError`: collect an error event with descriptive message, continue with next user
    - Construct `UserContext` directly (not via `from_user_entry`) since entry is a plain `UserEntry`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.1, 6.3, 6.4, 7.1_
  - [x] 3.3 Write property test for inactive entry processing (Property 1: Inactive entry processing disables all matching Flywheel users)
    - **Property 1: Inactive entry processing disables all matching Flywheel users**
    - **Validates: Requirements 1.1, 1.2, 1.4, 2.2**
    - Create `common/test/python/user_test/test_inactive_user_process.py`
    - Use Hypothesis to generate `UserEntry` objects with `active=False` and random lists of mock Flywheel users
    - Mock `FlywheelProxy.find_user_by_email` and `FlywheelProxy.disable_user`
    - Verify `disable_user` is called exactly once per matching user, and not called when match list is empty
  - [ ]* 3.4 Write property test for successful disable events (Property 5: Successful disable produces correctly-shaped success event)
    - **Property 5: Successful disable produces correctly-shaped success event**
    - **Validates: Requirements 6.1, 6.4**
    - Add to `common/test/python/user_test/test_inactive_user_process.py`
    - Use Hypothesis to generate inactive `UserEntry` and `CenterUserEntry` objects with mock Flywheel users
    - Verify collected success events have category `USER_DISABLED` and `UserContext` with correct email, name, and center_id
  - [ ]* 3.5 Write property test for failed disable events (Property 6: Failed disable produces error event)
    - **Property 6: Failed disable produces error event**
    - **Validates: Requirements 6.3**
    - Add to `common/test/python/user_test/test_inactive_user_process.py`
    - Use Hypothesis to generate inactive `UserEntry` objects
    - Configure mock `disable_user` to raise `FlywheelError`
    - Verify an error event is collected with a descriptive message and the entry's email in `UserContext`

- [x] 4. Wire environment through `UserProcess` to `InactiveUserProcess`
  - [x] 4.1 Update `UserProcess.execute` to pass environment to `InactiveUserProcess`
    - Change `InactiveUserProcess(self.collector)` to `InactiveUserProcess(self.__env, self.collector)`
    - _Requirements: 2.3_
  - [ ]* 4.2 Write unit tests for environment wiring and log preservation
    - Add to `common/test/python/user_test/test_inactive_user_process.py`
    - Verify `InactiveUserProcess` accepts both `UserProcessEnvironment` and `UserEventCollector` (Req 2.1)
    - Verify `UserProcess.execute` passes environment to `InactiveUserProcess` (Req 2.3)
    - Verify the "processing inactive entry" log message appears before disable attempts (Req 7.1)
    - Verify disable log includes user ID and email (Req 1.3)
    - _Requirements: 1.3, 2.1, 2.3, 7.1_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses Python — no language selection needed
- Registry cleanup (COManage) and REDCap removal are explicitly out of scope
