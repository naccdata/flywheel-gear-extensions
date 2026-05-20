# Implementation Plan: Authorization Resource Hierarchy

## Overview

Implement the `ResourceHierarchySeeder` class and integrate it into the `project_management` gear's existing project creation flow. The seeder calls `set_resource_parents` on the Authorization API for every resource (data pipeline, dashboard, page) the gear creates or visits, establishing parent relationships that enable inherited permissions via OpenFGA.

## Tasks

- [x] 1. Extend PageConfig to support community level
  - [x] 1.1 Add `"community"` to the `PageConfig.level` Literal type
    - Modify `common/src/python/projects/study.py` to change `PageConfig.level` from `Literal["center", "study"]` to `Literal["center", "study", "community"]`
    - Ensure the default remains `"center"`
    - _Requirements: 12.1, 12.2, 12.4_

  - [x] 1.2 Write unit tests for PageConfig community level
    - Test that `PageConfig(name="test", level="community")` passes validation
    - Test that plain string pages still default to `level="center"`
    - Test that invalid level values are rejected
    - _Requirements: 12.1, 12.2, 12.4_

- [x] 2. Implement ResourceHierarchySeeder class
  - [x] 2.1 Create the `ResourceHierarchySeeder` class with scope-specific seed methods
    - Create new file `gear/project_management/src/python/project_app/hierarchy_seeder.py`
    - Implement `__init__(self, client: AuthorizationClient)` storing the client and initializing `_failure_count = 0`
    - Implement `seed_center_pipeline(resource_id, study_id, center_id)` — calls `set_resource_parents` with `parent_study` and `parent_center`
    - Implement `seed_center_dashboard(resource_id, study_id, center_id)` — calls `set_resource_parents` with `parent_study` and `parent_center`
    - Implement `seed_center_page(resource_id, study_id, center_id)` — calls `set_resource_parents` with `parent_study` and `parent_center`
    - Implement `seed_study_dashboard(resource_id, study_id)` — calls `set_resource_parents` with `parent_study` only
    - Implement `seed_study_page(resource_id, study_id)` — calls `set_resource_parents` with `parent_study` only
    - Implement `seed_community_page(resource_id)` — calls `set_resource_parents` with `parent_community` (parent_id `"nacc"`)
    - Implement `failure_count` property
    - Each method wraps the API call in try/except, logs debug on success, logs error on failure, increments `_failure_count`
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 6.2, 7.1, 7.2, 7.3, 10.1, 10.2_

  - [x] 2.2 Write property test for scope-to-parents mapping correctness
    - **Property 1: Scope-to-parents mapping correctness**
    - Generate (resource_type, scope, study_id, center_id) tuples, call the appropriate seed method, assert the mock client received the correct parents list
    - **Validates: Requirements 1.1, 2.1, 3.1, 4.1, 5.1, 8.1, 8.2, 12.3**

  - [x] 2.3 Write property test for non-propagation of client exceptions
    - **Property 4: Non-propagation of client exceptions**
    - Generate random `AuthorizationClientError` subclass instances, configure mock to raise, verify no exception escapes the seeder
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 2.4 Write property test for failure count accuracy
    - **Property 5: Failure count accuracy**
    - Generate N resources with K configured to fail, verify `failure_count == K`
    - **Validates: Requirements 7.3**

  - [ ]* 2.5 Write property test for log messages contain identifying information
    - **Property 6: Log messages contain identifying information**
    - Generate random resource info, verify log records contain resource type, resource ID, and parent relationships (success) or exception description (failure)
    - **Validates: Requirements 10.1, 10.2**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Modify main.py to accept optional AuthorizationClient
  - [x] 4.1 Update `run()` function signature and seeder instantiation
    - Add `authorization_client: Optional[AuthorizationClient] = None` parameter to `run()`
    - If `authorization_client` is None, log a warning that hierarchy seeding is disabled and set `seeder = None`
    - Otherwise, create `ResourceHierarchySeeder(client=authorization_client)` and pass to `StudyMappingVisitor`
    - After visitor completes, check `seeder.failure_count` and log a warning if > 0
    - _Requirements: 9.2, 11.1, 11.3, 7.3_

  - [x] 4.2 Modify `StudyMappingVisitor.__init__` to accept optional `ResourceHierarchySeeder`
    - Add `hierarchy_seeder: Optional[ResourceHierarchySeeder] = None` parameter
    - Store as `self.__hierarchy_seeder`
    - _Requirements: 9.1, 9.2_

  - [x] 4.3 Write unit tests for main.py with optional client
    - Test that `run()` with `authorization_client=None` logs warning and does not call seeder
    - Test that `run()` with a valid client creates seeder and passes to visitor
    - Test that failure count warning is logged when failures occur
    - _Requirements: 11.1, 11.3, 7.3_

- [x] 5. Integrate seeder calls into StudyMappingVisitor
  - [x] 5.1 Add seeder calls for center-scoped data pipelines
    - In the pipeline creation flow (after `map_center_pipelines` calls), invoke `hierarchy_seeder.seed_center_pipeline()` for each pipeline project label
    - Pass the Flywheel project label as `resource_id`, `study_id` from `StudyModel`, and `center_id` from the center being visited
    - Only call if `self.__hierarchy_seeder` is not None
    - _Requirements: 1.1, 1.2, 8.3, 9.1_

  - [x] 5.2 Add seeder calls for center-scoped dashboards and pages
    - In `__handle_dashboards_and_pages`, after creating each center-level dashboard, call `hierarchy_seeder.seed_center_dashboard()` with the dashboard label, study_id, and center_id
    - After creating each center-level page, call `hierarchy_seeder.seed_center_page()` with the page label, study_id, and center_id
    - Skip seeding for inactive centers (already handled by existing guard)
    - Only call if `self.__hierarchy_seeder` is not None
    - _Requirements: 2.1, 2.2, 2.3, 8.1, 8.4, 9.1_

  - [x] 5.3 Add seeder calls for study-scoped dashboards and pages
    - In `visit_study` (after center iteration), iterate study-level dashboards and call `hierarchy_seeder.seed_study_dashboard()` with the derived label and study_id
    - Iterate study-level pages and call `hierarchy_seeder.seed_study_page()` with the derived label and study_id
    - Only call if `self.__hierarchy_seeder` is not None
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 8.1, 8.2, 9.1_

  - [x] 5.4 Add seeder calls for community-scoped pages
    - In `visit_study`, iterate community-level pages and call `hierarchy_seeder.seed_community_page()` with the derived page label
    - Ensure community pages do NOT get `parent_study` or `parent_center` relationships
    - Only call if `self.__hierarchy_seeder` is not None
    - _Requirements: 5.1, 5.2, 12.3, 9.1_

  - [ ]* 5.5 Write property test for resource ID derivation
    - **Property 2: Resource ID derivation follows label pattern**
    - Generate (resource_type, name, study_type, study_id), compute expected label, verify it matches what the seeder receives
    - **Validates: Requirements 1.2, 2.2, 3.2, 4.2, 5.2**

  - [ ]* 5.6 Write property test for idempotent execution
    - **Property 3: Idempotent execution**
    - Generate a study config, run seeder twice via the visitor, assert call lists are identical
    - **Validates: Requirements 6.1, 6.3**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integrate AuthorizationClient creation into run.py
  - [x] 7.1 Add client creation with error handling in `ProjectCreationVisitor.run()`
    - Import `create_authorization_client` and `ConfigurationError` from the `authorization` package
    - Wrap `create_authorization_client()` in try/except `ConfigurationError`
    - On failure, log error with reason and set `authorization_client = None`
    - Pass `authorization_client` to `main.run()`
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 7.2 Write unit tests for run.py client creation
    - Test successful client creation passes client to `main.run()`
    - Test `ConfigurationError` results in None client and error log
    - Test missing config results in None client and warning log
    - _Requirements: 11.1, 11.2_

- [x] 8. Add BUILD file for hierarchy_seeder module
  - [x] 8.1 Create or update BUILD file for the new hierarchy_seeder module
    - Add `python_sources` target for `gear/project_management/src/python/project_app/hierarchy_seeder.py`
    - Add dependency on the `authorization` package
    - _Requirements: 9.1_

- [x] 9. Integration tests
  - [x] 9.1 Write integration test with mock AuthorizationClient
    - Create `gear/project_management/test/python/test_hierarchy_seeder_integration.py`
    - Test full gear run with a representative StudyModel containing center-scoped pipelines, center-scoped dashboards, study-scoped dashboards, study-scoped pages, and community-scoped pages
    - Verify the complete set of `set_resource_parents` calls matches expected (resource_type, resource_id, parents) tuples
    - Verify seeding happens within the same gear execution as project creation
    - _Requirements: 9.1, 6.1, 6.3_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `authorization` package (from authorization-client-library spec) is assumed to already exist at `common/src/python/authorization/`
- All code uses Python 3.12 with Pydantic v2 models

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "2.3", "2.4", "2.5", "8.1"] },
    { "id": 2, "tasks": ["3", "4.1", "4.2"] },
    { "id": 3, "tasks": ["4.3", "5.1", "5.2"] },
    { "id": 4, "tasks": ["5.3"] },
    { "id": 5, "tasks": ["5.4", "5.5", "5.6"] },
    { "id": 6, "tasks": ["6", "7.1"] },
    { "id": 7, "tasks": ["7.2", "9.1"] },
    { "id": 8, "tasks": ["10"] }
  ]
}
```
