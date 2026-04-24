# Implementation Plan: Archive Contact Filter Bypass

## Overview

Modify three filtering points in the pull-directory gear so that archived contacts (`archive_contact='1'`) bypass `permissions_approval` and `signed_agreement_status_num_ct` checks, allowing them to flow through the pipeline and appear in the output YAML with `active: false`. Changes are scoped to `filter_approved_records()` and `run()` in `gear/pull_directory/src/python/directory_app/main.py`, and `to_user_entry()` in `common/src/python/users/nacc_directory.py`.

## Tasks

- [x] 1. Modify `filter_approved_records()` to allow archived contacts through pre-filter
  - [x] 1.1 Update the list comprehension filter in `filter_approved_records()` in `gear/pull_directory/src/python/directory_app/main.py`
    - Change the filter predicate from `record.get("permissions_approval") == "1"` to `record.get("permissions_approval") == "1" or record.get("archive_contact") == "1"`
    - Update the docstring to reflect the new behavior
    - _Requirements: 1.1, 1.2_

  - [ ]* 1.2 Write property test for pre-filter retention logic
    - **Property 1: Pre-filter retains a record iff it is archived or approved**
    - Generate random record dicts with varying `archive_contact` and `permissions_approval` values using Hypothesis
    - Assert `filter_approved_records` retains the record if and only if `archive_contact == '1'` or `permissions_approval == '1'`
    - Add test to `gear/pull_directory/test/python/test_filter_approved_records.py`
    - **Validates: Requirements 1.1, 1.2**

  - [x] 1.3 Write unit tests for pre-filter with archived contacts
    - Add example-based tests to `gear/pull_directory/test/python/test_filter_approved_records.py`
    - Test: archived record with `permissions_approval='0'` is retained
    - Test: archived record with `permissions_approval='1'` is retained
    - Test: non-archived record with `permissions_approval='0'` is excluded (existing behavior preserved)
    - _Requirements: 1.1, 1.2, 4.1_

- [x] 2. Modify `to_user_entry()` to check inactive status before guard clauses
  - [x] 2.1 Reorder `to_user_entry()` in `common/src/python/users/nacc_directory.py`
    - Move the `if self.inactive` block above the `if not self.signed_user_agreement` and `if not self.permissions_approval` guard clauses
    - When `inactive` is `True`, return `UserEntry(active=False)` immediately, before checking `signed_user_agreement` or `permissions_approval`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3_

  - [ ]* 2.2 Write property test for inactive record user entry conversion
    - **Property 4: to_user_entry returns correct UserEntry for inactive records**
    - Generate `DirectoryAuthorizations` objects with `inactive=True` and random `signed_user_agreement`/`permissions_approval` values
    - Assert result is a `UserEntry` (not `None`) with `active == False`, and `name`, `email`, `auth_email`, `approved` fields match the source object
    - Add test to `common/test/python/user_test/test_directory_authorizations.py`
    - **Validates: Requirements 3.1, 5.1, 5.2, 5.3**

  - [ ]* 2.3 Write property test for non-inactive records missing approval or agreement
    - **Property 5: to_user_entry returns None for non-inactive records missing approval or agreement**
    - Generate `DirectoryAuthorizations` objects with `inactive=False` and at least one of `signed_user_agreement`/`permissions_approval` as `False`
    - Assert `to_user_entry()` returns `None`
    - Add test to `common/test/python/user_test/test_directory_authorizations.py`
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 2.4 Write property test for non-inactive approved records
    - **Property 6: to_user_entry returns active entry for non-inactive approved records**
    - Generate `DirectoryAuthorizations` objects with `inactive=False`, `signed_user_agreement=True`, `permissions_approval=True`
    - Assert `to_user_entry()` returns a non-None entry with `active == True`
    - Add test to `common/test/python/user_test/test_directory_authorizations.py`
    - **Validates: Requirements 3.4**

  - [x] 2.5 Write unit tests for `to_user_entry()` inactive bypass
    - Add example-based tests to `common/test/python/user_test/test_directory_authorizations.py`
    - Test: archived record with both flags false produces `UserEntry` with `active=False` (not `None`)
    - Test: archived record produces `UserEntry` (not `ActiveUserEntry` or `CenterUserEntry`)
    - Test: non-archived record with both flags true and `adcid` produces `CenterUserEntry`
    - Test: non-archived record with both flags true and no `adcid` produces `ActiveUserEntry`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3_

- [x] 3. Modify `run()` to bypass approval and agreement checks for inactive records
  - [x] 3.1 Wrap approval and agreement checks in `run()` in `gear/pull_directory/src/python/directory_app/main.py`
    - Add `if not dir_record.inactive:` guard around both the `permissions_approval` check block and the `signed_user_agreement` check block
    - When `inactive` is `True`, skip both checks and proceed directly to `to_user_entry()`
    - The existing `assert entry is not None` remains valid because `to_user_entry()` now returns a `UserEntry` for inactive records
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 3.2 Write property test for run function bypassing checks for inactive records
    - **Property 2: Run function bypasses approval and agreement checks for inactive records**
    - Generate valid record dicts with `archive_contact='1'` and random `permissions_approval`/`signed_agreement_status_num_ct` values
    - Run through `run()` and assert the output YAML contains an entry for each archived record
    - Add test to `gear/pull_directory/test/python/test_integration_directory_error_handling.py`
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 3.3 Write property test for run function excluding non-inactive records missing approval or agreement
    - **Property 3: Run function excludes non-inactive records missing approval or agreement**
    - Generate valid record dicts with `archive_contact='0'` and at least one of `permissions_approval`/`signed_agreement_status_num_ct` falsy
    - Run through `run()` and assert the record is excluded from output and an error event is collected
    - Add test to `gear/pull_directory/test/python/test_integration_directory_error_handling.py`
    - **Validates: Requirements 2.3, 2.4**

  - [x] 3.4 Write integration tests for end-to-end archived contact processing
    - Add integration tests to `gear/pull_directory/test/python/test_integration_directory_error_handling.py`
    - Test: mix of archived and non-archived records through `run()`, verify output YAML contains correct entries with correct `active` and `approved` values
    - Test: non-archived records produce identical YAML output to current implementation (regression)
    - Test: archived record without approval or agreement produces entry with `active: false` and `approved: false`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- The implementation order (pre-filter → to_user_entry → run) ensures each layer is ready before the next depends on it
- No new modules, classes, or external dependencies are introduced
