# Implementation Plan: Study Page Resources

## Overview

This implementation adds study-specific page resource support to the project management gear, following the exact pattern established for dashboard resources in v2.3.0. The feature enables the ADRC Portal to control access to study-specific pages through Flywheel's project-based authorization system.

The implementation involves three main components:
1. Extend StudyModel to accept optional pages field from YAML configuration
2. Create PageProjectMetadata class with visitor pattern support
3. Add page creation logic to StudyMapper following dashboard pattern

All changes follow the existing dashboard implementation pattern to maintain codebase consistency.

## Task Dependencies

### Parallel Execution Groups

**Group A (Independent - Can run in parallel):**
- Task 1: Extend StudyModel
- Task 2: Create PageProjectMetadata class
- Task 3: Extend AbstractCenterMetadataVisitor

**Group B (Depends on Group A):**
- Task 4: Implement visit_page_project in GatherIngestDatatypesVisitor (depends on Task 2, 3)
- Task 5: Extend CenterStudyMetadata (depends on Task 2)
- Task 7: Add page_label() to StudyMapper (depends on Task 1)

**Group C (Depends on Group B):**
- Task 8: Implement __add_page() (depends on Task 5, 7)

**Group D (Depends on Group C):**
- Task 9: Update map_center_pipelines() (depends on Task 8)

**Group E (Depends on all implementation tasks):**
- Task 11: Integration tests (depends on Tasks 1-9)
- Task 12: Test builders and mocks (can start after Task 1)

**Checkpoints:**
- Task 6: Checkpoint after Group B
- Task 10: Checkpoint after Group D
- Task 13: Final checkpoint after all tasks

### Dependency Graph

```
Task 1 (StudyModel) ────────────────┐
                                     ├──> Task 7 (page_label) ──┐
Task 2 (PageProjectMetadata) ───┬───┤                           │
                                 │   └──> Task 5 (CenterStudy) ─┼──> Task 8 (__add_page) ──> Task 9 (map_center_pipelines) ──> Task 11 (Integration)
Task 3 (AbstractVisitor) ────────┤                               │
                                 │                               │
                                 └──> Task 4 (GatherVisitor) ────┘

Task 12 (Test builders) can start after Task 1 and run in parallel with other tasks
```

## Tasks

- [ ] 1. Extend StudyModel to accept pages field
  - **Dependencies:** None (can start immediately)
  - **Blocks:** Task 7, Task 12
  - Add `pages: Optional[List[str]] = None` field to StudyModel class in `common/src/python/projects/study.py`
  - Ensure Pydantic validation accepts list of strings or None
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ]* 1.1 Write property test for StudyModel YAML parsing
  - **Dependencies:** Task 1
  - **Can run in parallel with:** Tasks 1.2, 1.3
  - **Property 1: YAML Parsing Round-Trip**
  - **Validates: Requirements 1.1, 1.5**
  - Generate random StudyModel instances with pages field
  - Serialize to YAML and parse back, verify pages field matches
  - Minimum 100 iterations
  - Tag: `Feature: study-page-resources, Property 1: YAML Parsing Round-Trip`

- [ ]* 1.2 Write property test for invalid page names rejection
  - **Dependencies:** Task 1
  - **Can run in parallel with:** Tasks 1.1, 1.3
  - **Property 2: Invalid Page Names Rejected**
  - **Validates: Requirements 1.4**
  - Generate invalid pages lists (empty strings, None, non-strings)
  - Verify Pydantic validation raises error
  - Minimum 100 iterations
  - Tag: `Feature: study-page-resources, Property 2: Invalid Page Names Rejected`

- [ ]* 1.3 Write unit tests for StudyModel pages field
  - **Dependencies:** Task 1
  - **Can run in parallel with:** Tasks 1.1, 1.2
  - Test parsing YAML with pages field
  - Test parsing YAML without pages field
  - Test parsing YAML with empty pages list
  - Test validation rejects invalid page names
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Create PageProjectMetadata class and visitor support
  - **Dependencies:** None (can start immediately)
  - **Blocks:** Tasks 3, 4, 5, 8
  - [x] 2.1 Add PageProjectMetadata class to `common/src/python/centers/center_group.py`
    - **Dependencies:** None
    - **Blocks:** Tasks 2.2, 2.3, 2.4, 3, 4, 5
    - Create class inheriting from ProjectMetadata
    - Add `page_name: str` field
    - Implement `apply(visitor)` method that calls `visitor.visit_page_project(self)`
    - Place after DashboardProjectMetadata class (around line 508)
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 4.1, 4.2_

  - [ ]* 2.2 Write property test for PageProjectMetadata structure
    - **Dependencies:** Task 2.1
    - **Can run in parallel with:** Tasks 2.3, 2.4
    - **Property 9: PageProjectMetadata Structure**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5**
    - Generate random PageProjectMetadata instances
    - Verify all required fields present and non-empty
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 9: PageProjectMetadata Structure`

  - [ ]* 2.3 Write property test for visitor pattern invocation
    - **Dependencies:** Task 2.1
    - **Can run in parallel with:** Tasks 2.2, 2.4
    - **Property 10: Visitor Pattern Invocation**
    - **Validates: Requirements 4.2, 4.5**
    - Generate random PageProjectMetadata and visitor implementations
    - Call apply() and verify visit_page_project() invoked
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 10: Visitor Pattern Invocation`

  - [ ]* 2.4 Write unit tests for PageProjectMetadata
    - **Dependencies:** Task 2.1
    - **Can run in parallel with:** Tasks 2.2, 2.3
    - Test creation with all required fields
    - Test visitor pattern apply() method
    - Test serialization/deserialization
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 4.1, 4.2_

- [x] 3. Extend AbstractCenterMetadataVisitor interface
  - **Dependencies:** Task 2.1 (needs PageProjectMetadata type)
  - **Blocks:** Task 4
  - Add `visit_page_project(project: PageProjectMetadata)` abstract method to AbstractCenterMetadataVisitor in `common/src/python/centers/center_group.py`
  - Place after `visit_dashboard_project()` method
  - _Requirements: 4.3, 4.4_

- [x] 4. Implement visit_page_project in GatherIngestDatatypesVisitor
  - **Dependencies:** Tasks 2.1, 3
  - Add `visit_page_project()` method to GatherIngestDatatypesVisitor in `common/src/python/centers/center_group.py`
  - Implement as no-op (pass) since page projects don't contain datatypes
  - Place after `visit_dashboard_project()` method (around line 832)
  - _Requirements: 4.5_

- [ ]* 4.1 Write unit test for GatherIngestDatatypesVisitor
  - **Dependencies:** Task 4
  - Test that visit_page_project() is callable and doesn't affect datatype gathering
  - _Requirements: 4.5_

- [x] 5. Extend CenterStudyMetadata for page storage
  - **Dependencies:** Task 2.1 (needs PageProjectMetadata type)
  - **Blocks:** Task 8
  - [x] 5.1 Add page_projects field and methods to CenterStudyMetadata
    - **Dependencies:** Task 2.1
    - **Blocks:** Tasks 5.2, 5.3, 5.4, 8
    - Add `page_projects: Optional[Dict[str, PageProjectMetadata]] = {}` field
    - Add `add_page(project: PageProjectMetadata)` method
    - Add `get_page(project_label: str)` method
    - Follow exact pattern of dashboard_projects implementation
    - _Requirements: 3.1, 3.6, 3.7, 7.2, 7.3_

  - [ ]* 5.2 Write property test for metadata storage and retrieval
    - **Dependencies:** Task 5.1
    - **Can run in parallel with:** Tasks 5.3, 5.4
    - **Property 8: Metadata Storage and Retrieval**
    - **Validates: Requirements 3.1, 3.6, 3.7, 7.3**
    - Generate random PageProjectMetadata instances
    - Store and retrieve by label, verify matches original
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 8: Metadata Storage and Retrieval`

  - [ ]* 5.3 Write property test for multiple pages storage
    - **Dependencies:** Task 5.1
    - **Can run in parallel with:** Tasks 5.2, 5.4
    - **Property 14: Multiple Page Projects Stored**
    - **Validates: Requirements 7.2**
    - Generate studies with multiple page names
    - Verify all stored in dictionary with correct keys
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 14: Multiple Page Projects Stored`

  - [ ]* 5.4 Write unit tests for CenterStudyMetadata page methods
    - **Dependencies:** Task 5.1
    - **Can run in parallel with:** Tasks 5.2, 5.3
    - Test add_page() method
    - Test get_page() method
    - Test page_projects dictionary initialization
    - Test multiple pages storage
    - _Requirements: 3.1, 3.6, 3.7, 7.2, 7.3_

- [ ] 6. Checkpoint - Ensure all tests pass
  - **Dependencies:** Tasks 1-5 and their sub-tasks
  - **Blocks:** Task 7
  - Run all unit tests and property tests created so far
  - Verify no regressions in existing functionality
  - Ask user if questions arise

- [x] 7. Add page creation logic to StudyMapper
  - **Dependencies:** Task 1 (needs StudyModel.pages field)
  - **Blocks:** Task 8
  - [x] 7.1 Add page_label() method to StudyMapper
    - **Dependencies:** Task 1
    - **Blocks:** Tasks 7.2, 7.3, 7.4, 8
    - Create method that returns `f"page-{page_name}{self.study.project_suffix()}"`
    - Place after dashboard_label() method in `common/src/python/projects/study_mapping.py` (around line 97)
    - _Requirements: 2.2, 2.3, 8.1, 8.2, 8.4, 8.5_

  - [ ]* 7.2 Write property test for primary study label format
    - **Dependencies:** Task 7.1
    - **Can run in parallel with:** Tasks 7.3, 7.4
    - **Property 4: Primary Study Label Format**
    - **Validates: Requirements 2.2, 8.1, 8.4**
    - Generate random primary studies with random page names
    - Verify all labels match "page-{page_name}" format
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 4: Primary Study Label Format`

  - [ ]* 7.3 Write property test for affiliated study label format
    - **Dependencies:** Task 7.1
    - **Can run in parallel with:** Tasks 7.2, 7.4
    - **Property 5: Affiliated Study Label Format**
    - **Validates: Requirements 2.3, 8.2, 8.5**
    - Generate random affiliated studies with random page names
    - Verify all labels match "page-{page_name}-{study_id}" format
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 5: Affiliated Study Label Format`

  - [ ]* 7.4 Write unit tests for page_label() method
    - **Dependencies:** Task 7.1
    - **Can run in parallel with:** Tasks 7.2, 7.3
    - Test label generation for primary studies
    - Test label generation for affiliated studies
    - _Requirements: 2.2, 2.3, 8.1, 8.2, 8.4, 8.5_

- [ ] 8. Implement __add_page() method in StudyMapper
  - **Dependencies:** Tasks 5.1 (needs CenterStudyMetadata.add_page), 7.1 (needs page_label)
  - **Blocks:** Task 9
  - [ ] 8.1 Create __add_page() private method
    - **Dependencies:** Tasks 5.1, 7.1
    - **Blocks:** Tasks 8.2, 8.3, 9
    - Accept center, study_info, and page_name parameters
    - Create update_page() closure that calls study_info.add_page()
    - Call self.add_pipeline() with page label and update function
    - Place after __add_dashboard() method in `common/src/python/projects/study_mapping.py` (around line 125)
    - Follow exact pattern of __add_dashboard() implementation
    - _Requirements: 2.1, 5.2, 5.3_

  - [ ]* 8.2 Write property test for page creation method calls
    - **Dependencies:** Task 8.1
    - **Can run in parallel with:** Task 8.3
    - **Property 12: Page Creation Method Called for Each Page**
    - **Validates: Requirements 5.2**
    - Generate studies with N pages
    - Mock page creation method
    - Verify method called exactly N times
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 12: Page Creation Method Called for Each Page`

  - [ ]* 8.3 Write unit tests for __add_page() method
    - **Dependencies:** Task 8.1
    - **Can run in parallel with:** Task 8.2
    - Test page project creation
    - Test metadata storage via update_page closure
    - Test error handling
    - _Requirements: 2.1, 5.2, 5.3_

- [ ] 9. Update map_center_pipelines() to create page projects
  - **Dependencies:** Task 8.1 (needs __add_page method)
  - **Blocks:** Task 11
  - [ ] 9.1 Add page creation logic to map_center_pipelines()
    - **Dependencies:** Task 8.1
    - **Blocks:** Tasks 9.2, 9.3, 9.4, 9.5, 11
    - Add code block after dashboard creation logic
    - Check if center is active and study has pages
    - Iterate through page names and call __add_page() for each
    - Follow exact pattern of dashboard creation block
    - _Requirements: 2.1, 2.4, 5.1, 5.5, 7.1, 7.4_

  - [ ]* 9.2 Write property test for page projects created for all pages
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 9.3, 9.4, 9.5
    - **Property 3: Page Projects Created for All Pages**
    - **Validates: Requirements 2.1, 7.1, 7.4**
    - Generate studies with N pages and M active centers
    - Run study mapping
    - Verify exactly N × M projects created
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 3: Page Projects Created for All Pages`

  - [ ]* 9.3 Write property test for inactive centers excluded
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 9.2, 9.4, 9.5
    - **Property 6: Inactive Centers Excluded**
    - **Validates: Requirements 2.4**
    - Generate studies with pages and mix of active/inactive centers
    - Verify no projects created for inactive centers
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 6: Inactive Centers Excluded`

  - [ ]* 9.4 Write property test for page projects created during mapping
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 9.2, 9.3, 9.5
    - **Property 11: Page Projects Created During Mapping**
    - **Validates: Requirements 5.1, 5.3, 5.5**
    - Generate studies with pages and active centers
    - Run map_center_pipelines()
    - Verify all page projects exist with metadata
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 11: Page Projects Created During Mapping`

  - [ ]* 9.5 Write unit tests for map_center_pipelines() with pages
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 9.2, 9.3, 9.4
    - Test page creation for studies with pages
    - Test no page creation for studies without pages
    - Test inactive center handling
    - _Requirements: 2.1, 2.4, 2.5, 5.1, 5.5_

- [ ] 10. Checkpoint - Ensure all tests pass
  - **Dependencies:** Tasks 7-9 and their sub-tasks
  - **Blocks:** Task 11
  - Run complete test suite including all property tests
  - Verify all 16 correctness properties pass with minimum 100 iterations each
  - Ask user if questions arise

- [ ] 11. Add integration tests
  - **Dependencies:** Task 9.1 (needs complete implementation)
  - [ ]* 11.1 Write property test for Flywheel project existence
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.2-11.7
    - **Property 7: Page Projects Exist in Flywheel**
    - **Validates: Requirements 2.6**
    - Generate random page projects
    - Create in Flywheel (mocked)
    - Verify projects exist with correct labels
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 7: Page Projects Exist in Flywheel`

  - [ ]* 11.2 Write property test for error logging
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.1, 11.3-11.7
    - **Property 13: Error Logging on Failure**
    - **Validates: Requirements 5.4**
    - Generate random page project creation failures
    - Verify error messages contain center ID and label
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 13: Error Logging on Failure`

  - [ ]* 11.3 Write property test for unique project labels
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.1, 11.2, 11.4-11.7
    - **Property 15: Unique Project Labels**
    - **Validates: Requirements 7.5**
    - Generate random page projects for a center
    - Verify all labels are unique
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 15: Unique Project Labels`

  - [ ]* 11.4 Write property test for multiple study types
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.1-11.3, 11.5-11.7
    - **Property 16: Multiple Study Types Handled**
    - **Validates: Requirements 8.3**
    - Generate centers with both primary and affiliated studies
    - Verify correct naming for both study types
    - Minimum 100 iterations
    - Tag: `Feature: study-page-resources, Property 16: Multiple Study Types Handled`

  - [ ]* 11.5 Write end-to-end integration test
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.1-11.4, 11.6, 11.7
    - Create test study YAML with pages field
    - Run complete study mapping process
    - Verify page projects created with correct labels
    - Verify metadata stored correctly
    - _Requirements: 2.1, 2.6, 3.1, 5.1, 5.5_

  - [ ]* 11.6 Write multi-study integration test
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.1-11.5, 11.7
    - Create primary study with pages
    - Create affiliated study with pages
    - Map both studies to same center
    - Verify correct project labels for both
    - Verify no label conflicts
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 11.7 Write error recovery integration test
    - **Dependencies:** Task 9.1
    - **Can run in parallel with:** Tasks 11.1-11.6
    - Simulate Flywheel API failures during page creation
    - Verify error logging includes center ID and label
    - Verify partial success (other pages still created)
    - Verify system remains in consistent state
    - _Requirements: 5.4_

- [ ] 12. Create test data builders and mock factories
  - **Dependencies:** Task 1 (needs StudyModel)
  - **Can run in parallel with:** Tasks 2-11 (after Task 1 completes)
  - [ ]* 12.1 Create StudyModelBuilder for test data
    - **Dependencies:** Task 1
    - **Can run in parallel with:** Tasks 12.2, 12.3
    - Implement builder with fluent interface
    - Support with_pages() and with_study_type() methods
    - Provide sensible defaults
    - Place in test utilities module

  - [ ]* 12.2 Create PageProjectMetadataBuilder for test data
    - **Dependencies:** Task 2.1
    - **Can run in parallel with:** Tasks 12.1, 12.3
    - Implement builder with fluent interface
    - Support with_page_name() and with_study_id() methods
    - Provide sensible defaults
    - Place in test utilities module

  - [ ]* 12.3 Create mock factories for Flywheel components
    - **Dependencies:** None (uses existing types)
    - **Can run in parallel with:** Tasks 12.1, 12.2
    - Create mock_flywheel_proxy fixture
    - Create create_mock_project() factory
    - Create create_mock_center() factory
    - Centralize in conftest.py or test utilities

- [ ] 13. Final checkpoint - Ensure all tests pass
  - **Dependencies:** All tasks (1-12)
  - Run complete test suite with all unit, property, and integration tests
  - Verify all 16 correctness properties pass with minimum 100 iterations
  - Verify no regressions in existing functionality
  - Run code quality checks (lint, type check)
  - Ask user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end workflows
- Implementation follows exact dashboard pattern for consistency
- All visitor implementations must be updated to support page projects
- Test data builders and mock factories improve test maintainability
