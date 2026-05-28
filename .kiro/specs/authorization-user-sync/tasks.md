# Implementation Plan: Authorization User Sync

## Overview

Implement the authorization sync module that translates the gear's Activity vocabulary to Authorization API grants and synchronizes user grants via a diff-based process. The module integrates with the existing user processing pipeline as an optional dependency on `UserProcessEnvironment`.

## Tasks

- [x] 1. Create authorization_sync module structure and data models
  - [x] 1.1 Create module directory and DesiredGrant dataclass
    - Create `common/src/python/authorization_sync/__init__.py` with public exports
    - Create `common/src/python/authorization_sync/models.py` with the frozen `DesiredGrant` dataclass (user_id, resource_type, resource_id, relation)
    - Create `common/src/python/authorization_sync/BUILD` with `python_sources(name="lib")`
    - _Requirements: 3.3, 5.4_

  - [x] 1.2 Add AUTHORIZATION_SYNC EventCategory value
    - Add `AUTHORIZATION_SYNC = "Authorization Sync"` to the `EventCategory` enum in `common/src/python/users/event_models.py`
    - _Requirements: 9.3_

- [x] 2. Implement the ActivityTranslator
  - [x] 2.1 Implement the translate function and ACTIVITY_RELATION_MAP
    - Create `common/src/python/authorization_sync/translator.py`
    - Define `ACTIVITY_RELATION_MAP` as a module-level constant mapping `(action, resource_prefix)` tuples to `list[tuple[str, str]]` pairs
    - Implement `translate(registry_id, authorizations, center_group_id=None)` that iterates activities, looks up mappings, constructs resource IDs with proper scoping, and returns `set[DesiredGrant]`
    - Center-scoped: resource_id = `{center_group_id}/{project_label}`
    - General: resource_id = `{project_label}`
    - Log warnings for unmapped activities and skip without raising
    - Return deduplicated set (frozen dataclass provides __hash__/__eq__)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 10.1, 10.2, 10.3_

  - [x] 2.2 Write property test: Activity-to-relation mapping correctness
    - __Property 1: Activity-to-relation mapping correctness__
    - __Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 10.1, 10.3__

  - [ ]* 2.3 Write property test: Resource ID scoping
    - __Property 2: Resource ID scoping__
    - __Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.2__

  - [ ]* 2.4 Write property test: Output deduplication
    - __Property 3: Output deduplication__
    - __Validates: Requirements 3.5, 10.2__

  - [ ]* 2.5 Write property test: Unmapped activities are skipped without error
    - __Property 4: Unmapped activities are skipped without error__
    - __Validates: Requirements 2.5, 3.4__

- [x] 3. Implement AuthorizationSyncService
  - [x] 3.1 Implement permissions parsing and diff computation
    - Create `common/src/python/authorization_sync/sync_service.py`
    - Implement `_parse_current_grants(user_id, permissions)` that converts `UserPermissions` response into a flat `set[DesiredGrant]`
    - Implement `_compute_diff(desired, current)` returning `(grants_to_add, grants_to_revoke)` as set difference operations
    - Implement `grant_to_batch_op(grant, action)` helper that converts a `DesiredGrant` to a `BatchOperation`
    - _Requirements: 4.2, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1_

  - [ ]* 3.2 Write property test: Permissions response parsing
    - __Property 5: Permissions response parsing__
    - __Validates: Requirements 4.2__

  - [x] 3.3 Write property test: Diff computation correctness
    - __Property 6: Diff computation correctness__
    - __Validates: Requirements 5.1, 5.2, 5.3, 5.4__

  - [x] 3.4 Implement sync_user method with fault isolation
    - Implement `AuthorizationSyncService.__init__(client, collector)` storing the client and collector
    - Implement `sync_user(registry_id, authorizations, center_group_id=None)` orchestrating: translate → query → parse → diff → batch
    - Skip sync if registry_id is empty/None
    - Catch all `AuthorizationClientError` exceptions, log at error level, report via `UserEventCollector` with `EventCategory.AUTHORIZATION_SYNC`
    - Report partial failures (BatchResult.failed > 0) as individual error events
    - Log info on success with counts of grants added/revoked
    - _Requirements: 4.1, 4.3, 4.4, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4, 9.1, 9.2, 9.3, 9.4_

  - [ ]* 3.5 Write property test: Batch construction from diff
    - __Property 7: Batch construction from diff__
    - __Validates: Requirements 6.1, 6.2__

  - [x] 3.6 Write property test: Fault isolation with event reporting
    - __Property 8: Fault isolation with event reporting__
    - __Validates: Requirements 4.3, 7.1, 7.3, 7.4, 9.2__

- [x] 4. Integrate with UserProcessEnvironment and process classes
  - [x] 4.1 Add authorization_sync field to UserProcessEnvironment
    - Add optional `authorization_sync: Optional[AuthorizationSyncService] = None` parameter to `UserProcessEnvironment.__init__`
    - Add `@property` accessor returning the optional service
    - _Requirements: 8.3, 8.4_

  - [x] 4.2 Invoke sync from UpdateCenterUserProcess
    - After `CenterAuthorizationVisitor` completes, call `authorization_sync.sync_user(registry_id, study_authorizations, center_group_id)` if the service is available
    - Skip if `authorization_sync` is None
    - Ensure existing Flywheel role assignment completes regardless of sync outcome
    - _Requirements: 8.1, 8.4, 8.5_

  - [x] 4.3 Invoke sync from UpdateUserProcess
    - After `GeneralAuthorizationVisitor` completes, call `authorization_sync.sync_user(registry_id, authorizations)` (no center_group_id) if the service is available
    - Skip if `authorization_sync` is None
    - Ensure existing Flywheel role assignment completes regardless of sync outcome
    - _Requirements: 8.2, 8.4, 8.5_

  - [x] 4.4 Write integration tests for pipeline integration
    - Test UpdateCenterUserProcess calls sync after visitor with correct arguments
    - Test UpdateUserProcess calls sync for general authorizations
    - Test sync failure does not prevent Flywheel role assignment
    - Test None sync service skips sync step
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

- [x] 5. Set up test infrastructure
  - [x] 5.1 Create test directory and shared fixtures
    - Create `common/test/python/authorization_sync_test/__init__.py`
    - Create `common/test/python/authorization_sync_test/conftest.py` with shared Hypothesis strategies (valid actions, Resource instances, center group IDs, project labels, registry IDs, DesiredGrant sets, UserPermissions responses)
    - Create `common/test/python/authorization_sync_test/BUILD` with `python_tests(name="tests")`
    - Create mock `AuthorizationClient` fixture for property tests
    - _Requirements: all (test infrastructure)_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The authorization client library (`common/src/python/authorization/`) already exists and provides `AuthorizationClient`, `BatchOperation`, `UserPermissions`, and exception types
- Test directory follows the `_test` suffix convention: `authorization_sync_test`
- The `translate()` function works with both `Authorizations` (general) and `StudyAuthorizations` (center-scoped) since `StudyAuthorizations` extends `Authorizations`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "5.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 4, "tasks": ["3.5", "3.6", "4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3"] },
    { "id": 6, "tasks": ["4.4"] }
  ]
}
```
