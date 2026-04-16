# Implementation Plan: Pull Directory Export Records

## Overview

Refactor the `pull_directory` gear to replace report-based data retrieval (`REDCapReportConnection.get_report_records()`) with field-based export (`REDCapProject.export_records()`). This involves adding a field name derivation function, switching the connection setup, adding client-side record filtering, and updating the visitor's `create()` method.

## Tasks

- [x] 1. Add `get_directory_field_names()` to `nacc_directory.py`
  - [x] 1.1 Implement `get_directory_field_names()` function in `common/src/python/users/nacc_directory.py`
    - Add a new function that iterates over `DirectoryAuthorizations.model_fields` and resolves each field's REDCap name
    - For fields with `validation_alias` containing `AliasChoices`, extract the first alias choice string
    - For fields with `alias`, use the alias value
    - Otherwise, use the Python field name
    - Deduplicate the resulting list (e.g., `web_report_access` maps to two Python fields)
    - Return a `list[str]` of unique REDCap field names
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 1.2 Write unit tests for `get_directory_field_names()`
    - Create `common/test/python/user_test/test_directory_field_names.py`
    - Test that the returned list contains all expected REDCap field names (snapshot against known fields from Requirement 1.2)
    - Test that `web_report_access` appears exactly once (deduplication)
    - Test that the list has no duplicates
    - Test that the count matches the number of unique REDCap field names expected from the model
    - _Requirements: 4.1, 4.3, 1.2_

  - [ ]* 1.3 Write property test: field derivation covers all model fields (Property 1)
    - Add to `common/test/python/user_test/test_directory_field_names.py`
    - **Property 1: Field derivation covers all model fields with correct aliases**
    - For every field in `DirectoryAuthorizations.model_fields`, assert its resolved REDCap name is in `get_directory_field_names()` output
    - Assert no duplicates in the output list
    - Use `hypothesis` with `@settings(max_examples=100)`
    - **Validates: Requirements 1.2, 4.1, 4.3**

- [x] 2. Add `filter_approved_records()` and update `DirectoryPullVisitor.create()`
  - [x] 2.1 Implement `filter_approved_records()` in `gear/pull_directory/src/python/directory_app/run.py`
    - Add a function that takes `list[dict[str, str]]` and returns only records where `permissions_approval == '1'`
    - Records missing the `permissions_approval` key should be excluded
    - _Requirements: 2.1, 2.2_

  - [x] 2.2 Refactor `DirectoryPullVisitor.create()` in `gear/pull_directory/src/python/directory_app/run.py`
    - Change import from `REDCapReportConnection` to `REDCapConnection` from `redcap_api.redcap_connection`
    - Add import for `REDCapProject` from `redcap_api.redcap_project`
    - Add import for `REDCapParameters` from `redcap_api.redcap_parameter_store`
    - Add import for `get_directory_field_names` from `users.nacc_directory`
    - Replace `parameter_store.get_redcap_report_parameters(param_path=param_path)` with `parameter_store.get_parameters(param_type=REDCapParameters, parameter_path=param_path)`
    - Replace `REDCapReportConnection.create_from(report_parameters)` + `get_report_records()` with `REDCapConnection.create_from(params)` + `REDCapProject.create(connection)` + `project.export_records(fields=get_directory_field_names())`
    - Apply `filter_approved_records()` to the exported records before passing to the constructor
    - Wrap `REDCapConnectionError` in `GearExecutionError` (same pattern as before)
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 2.3 Write unit tests for `filter_approved_records()`
    - Add to `gear/pull_directory/test/python/test_filter_approved_records.py`
    - Test with empty list returns empty list
    - Test with all approved records returns all records
    - Test with mixed approved/unapproved records returns only approved
    - Test with records missing `permissions_approval` key excludes those records
    - Test that record order is preserved
    - _Requirements: 2.1, 2.2_

  - [ ]* 2.4 Write property test: filtering retains only approved records (Property 2)
    - Add to `gear/pull_directory/test/python/test_filter_approved_records.py`
    - **Property 2: Filtering retains only approved records**
    - Generate random lists of dicts with `permissions_approval` values from `{'0', '1', '', 'Yes', 'No'}` and missing keys
    - Assert every output record has `permissions_approval == '1'`
    - Assert output is a subsequence of input (order preserved, no records added)
    - Assert output count equals count of input records where `permissions_approval == '1'`
    - Use `hypothesis` with `@settings(max_examples=100)`
    - **Validates: Requirements 2.1, 2.2**

  - [x] 2.5 Write unit tests for refactored `DirectoryPullVisitor.create()`
    - Add to `gear/pull_directory/test/python/test_directory_pull_visitor_create.py`
    - Mock `ParameterStore.get_parameters` to return `REDCapParameters` (url, token only — no reportid)
    - Mock `REDCapConnection.create_from` and verify it is called (not `REDCapReportConnection`)
    - Mock `REDCapProject.create` and `export_records` and verify `export_records` is called with `fields=get_directory_field_names()`
    - Verify `filter_approved_records()` is applied to the exported records
    - Test that `REDCapConnectionError` from `export_records` is wrapped in `GearExecutionError`
    - Test that `ParameterError` is wrapped in `GearExecutionError`
    - _Requirements: 1.1, 1.3, 3.1, 3.2, 3.3, 3.4, 5.1_

- [x] 3. Update existing tests for compatibility
  - [x] 3.1 Update `gear/pull_directory/test/python/test_integration_directory_error_handling.py`
    - Update `MockParameterStore` to use `get_parameters` instead of `get_redcap_report_parameters`
    - Remove `reportid` from mock REDCap params (only `url` and `token` needed)
    - Update `test_visitor_creation_with_error_handling_support` to mock `REDCapConnection.create_from`, `REDCapProject.create`, and `export_records` instead of `REDCapReportConnection.create_from`
    - Update `test_gear_handles_missing_user_filename` to use new mock pattern
    - Update `test_gear_handles_redcap_connection_error` to mock `REDCapConnection.create_from` or `REDCapProject.create`
    - Update `test_gear_handles_parameter_store_error` to mock `get_parameters` instead of `get_redcap_report_parameters`
    - Verify all existing tests pass with the refactored code
    - _Requirements: 5.1, 5.2, 5.3, 5.4_


## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `main.py` processing logic and YAML output format remain unchanged (Requirement 5)
