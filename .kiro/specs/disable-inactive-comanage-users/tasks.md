# Implementation Plan: Disable Inactive COmanage Users

## Overview

This plan implements the feature to suspend users in COmanage when they are marked inactive in the NACC directory, and re-enable suspended users who become active again. The implementation follows the existing codebase patterns: extending `UserRegistry` with update capability, modifying `InactiveUserProcess` to suspend in COmanage, and modifying `ActiveUserProcess` to detect and re-enable suspended users. All new write operations respect dry-run mode.

Sub-agents executing tasks should use the `kiro-pants-power` MCP tools (`pants_fix`, `pants_lint`, `pants_check`, `pants_test`) for all code quality operations rather than manual shell commands.

## Tasks

- [ ] 1. Add `is_suspended` method to `RegistryPerson` and dry-run support to `UserRegistry`
  - [ ] 1.1 Add `is_suspended()` method to `RegistryPerson` in `common/src/python/users/user_registry.py`
    - Add method that returns `True` when `CoPerson.status == "S"`, `False` otherwise
    - Follow the same pattern as the existing `is_active()` method
    - _Requirements: 4.1_
  - [ ] 1.2 Add `dry_run` parameter to `UserRegistry.__init__` in `common/src/python/users/user_registry.py`
    - Add `dry_run: bool = False` parameter to the constructor
    - Store as `self.__dry_run` private attribute
    - Add a `dry_run` property for read access
    - _Requirements: 5.1, 5.2_
  - [ ]* 1.3 Write unit tests for `RegistryPerson.is_suspended()` in `common/test/python/user_test/test_registry_person_status.py`
    - Test returns `True` for status `"S"`
    - Test returns `False` for status `"A"`, `"D"`, and `None`
    - Follow existing test patterns in `test_registry_person_status.py`
    - _Requirements: 4.1_

- [ ] 2. Implement `UserRegistry` status update methods
  - [ ] 2.1 Implement private `__get_person_message` method in `UserRegistry`
    - Retrieve the full `CoPersonMessage` for a given registry ID using `DefaultApi.get_co_person(coid, identifier=registry_id)`
    - Raise `RegistryError` if no record is found or the API call fails (`ApiException`)
    - _Requirements: 6.1, 1.1, 2.1_
  - [ ] 2.2 Implement private `__update_status` method in `UserRegistry`
    - Accept `registry_id: str` and `target_status: str` parameters
    - Raise `RegistryError` if `registry_id` is `None` or empty
    - Call `__get_person_message` to GET the full `CoPersonMessage`
    - Modify only `co_person.status` to `target_status` on the retrieved message
    - In dry-run mode: log the intended action (registry ID and target status) and return without calling PUT
    - In normal mode: call `DefaultApi.update_co_person(coid, identifier=registry_id, co_person_message=modified_message)`
    - Raise `RegistryError` wrapping `ApiException` if PUT fails
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3_
  - [ ] 2.3 Implement public `suspend` method in `UserRegistry`
    - Call `__update_status(registry_id, "S")`
    - Raise `RegistryError` if registry_id is missing or API calls fail
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 2.4 Implement public `re_enable` method in `UserRegistry`
    - Call `__update_status(registry_id, "A")`
    - Raise `RegistryError` if registry_id is missing or API calls fail
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ] 2.5 Write unit tests for `UserRegistry.suspend` and `re_enable`
    - Test suspend with valid registry ID calls GET then PUT with status `"S"`
    - Test re_enable with valid registry ID calls GET then PUT with status `"A"`
    - Test suspend with no registry ID raises `RegistryError`
    - Test suspend when GET returns no record raises `RegistryError`
    - Test suspend when PUT fails raises `RegistryError` with API error details
    - Test re_enable when GET fails raises `RegistryError`
    - Add tests to a new file `common/test/python/user_test/test_user_registry_update.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3_
  - [ ]* 2.6 Write property test for status update round-trip preservation
    - **Property 1: Status update round-trip preserves all non-status fields**
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.2, 6.1, 6.2, 6.3, 6.4**
    - Generate random `CoPersonMessage` objects using the existing `coperson_message_strategy` from `conftest.py`
    - Mock `DefaultApi.get_co_person` to return the generated message
    - Call `suspend` or `re_enable`
    - Capture the `CoPersonMessage` passed to the `update_co_person` mock
    - Assert all fields except `CoPerson.status` are identical between original and updated messages
    - Add to a new file `common/test/python/user_test/test_property_status_roundtrip.py`
    - Use `@settings(max_examples=100)` per project convention
  - [ ]* 2.7 Write property test for dry-run mode
    - **Property 4: Dry-run mode skips writes but performs reads**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - Generate random registry IDs and target statuses (`"S"` or `"A"`)
    - Enable dry-run on `UserRegistry`
    - Assert GET (`get_co_person`) is called but PUT (`update_co_person`) is not called
    - Add to a new file `common/test/python/user_test/test_property_dry_run.py`
    - Use `@settings(max_examples=100)` per project convention

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Extend `InactiveUserProcess` to suspend in COmanage
  - [ ] 4.1 Modify `InactiveUserProcess.visit` in `common/src/python/users/user_processes.py`
    - After the existing Flywheel disable logic, add COmanage suspension logic
    - Look up the user in COmanage by email using `self.__env.user_registry.get(email=entry.email)`
    - If no matching `RegistryPerson` found, log info and continue without error
    - For each matching `RegistryPerson` with a registry ID, call `self.__env.user_registry.suspend(registry_id)`
    - On success, collect a `UserProcessEvent` with `EventType.SUCCESS`, `EventCategory.USER_DISABLED`, and message `"User {registry_id} suspended in COmanage"`
    - On `RegistryError`, log the error and collect an error event with a message identifying COmanage and the error details
    - Flywheel disable and COmanage suspend must be independent — failure of one does not prevent the other
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [ ] 4.2 Write unit tests for `InactiveUserProcess` COmanage suspension
    - Test that COmanage suspend is attempted after Flywheel disable
    - Test that COmanage suspend is attempted even when Flywheel disable fails
    - Test that no error when no COmanage record found for user email
    - Test that success event is collected with COmanage-specific message
    - Test that error event is collected when COmanage suspend fails
    - Add tests to `common/test/python/user_test/test_inactive_user_process.py`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  - [ ]* 4.3 Write property test for Flywheel/COmanage independence
    - **Property 2: Flywheel disable and COmanage suspend are independent**
    - **Validates: Requirements 3.1, 3.3, 3.4**
    - Generate random inactive `UserEntry` objects and random Flywheel user lists
    - Parameterize Flywheel and COmanage to succeed or fail independently
    - Assert that each service's operation is attempted regardless of the other's outcome
    - Add to a new file `common/test/python/user_test/test_property_service_independence.py`
    - Use `@settings(max_examples=100)` per project convention

- [ ] 5. Extend `ActiveUserProcess` to re-enable suspended users
  - [ ] 5.1 Modify `ActiveUserProcess.visit` in `common/src/python/users/user_processes.py`
    - After the email lookup (`person_list = self.__env.user_registry.get(email=entry.auth_email)`) returns results, check if any `RegistryPerson` in the list has `is_suspended() == True`
    - If a suspended person is found, call `self.__env.user_registry.re_enable(registry_id)` instead of routing to claimed/unclaimed queues or creating a new record
    - On success, collect a `UserProcessEvent` with `EventType.SUCCESS`, `EventCategory.USER_DISABLED`, and message `"User {registry_id} re-enabled in COmanage"`
    - On `RegistryError`, collect an error event with failure details and continue processing
    - Only re-enable persons matched by the same email address (already guaranteed by the `get(email=...)` lookup)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [ ] 5.2 Write unit tests for `ActiveUserProcess` re-enable logic
    - Test that a suspended `RegistryPerson` matched by email is re-enabled
    - Test that `add` is not called when a suspended match exists
    - Test that success event is collected on re-enable
    - Test that error event is collected on re-enable failure and processing continues
    - Test that active (non-suspended) persons follow the existing claimed/unclaimed flow
    - Add tests to a new file `common/test/python/user_test/test_active_user_reenable.py`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [ ]* 5.3 Write property test for re-enable instead of duplicate creation
    - **Property 3: Active process re-enables suspended users instead of creating duplicates**
    - **Validates: Requirements 4.1, 4.2**
    - Generate random `ActiveUserEntry` objects and matching suspended `RegistryPerson` objects
    - Assert `re_enable` is called and `add` is not called
    - Add to a new file `common/test/python/user_test/test_property_reenable_no_duplicate.py`
    - Use `@settings(max_examples=100)` per project convention

- [ ] 6. Wire dry-run flag in gear entry point
  - [ ] 6.1 Update `UserRegistry` constructor call in `gear/user_management/src/python/user_app/run.py`
    - Pass `dry_run=self.proxy.dry_run` to the `UserRegistry` constructor in the `UserManagementVisitor.run` method
    - This ensures COmanage operations respect the same dry-run mode as Flywheel operations
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific scenarios and edge cases
- All code quality checks (fix, lint, check, test) are handled by hooks — no need for manual quality check sub-tasks
- Sub-agents should use the `kiro-pants-power` MCP tools for code quality operations
