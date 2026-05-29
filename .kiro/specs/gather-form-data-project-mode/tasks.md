# Implementation Plan: Gather Form Data — Project Mode

## Overview

Add a project-based execution mode to the gather-form-data gear. Implementation follows the existing gear architecture: a new `ProjectModeVisitor` in `run.py` handles Flywheel context and subject iteration, a `run_project_mode` function in `main.py` orchestrates testable business logic, and the manifest is updated to support the new mode with optional inputs.

## Tasks

- [ ] 1. Update manifest and add ProjectModeConfig model
  - [ ] 1.1 Update gear manifest for project mode support
    - Add `execution_mode` config with enum `["participant_list", "project"]` and default `"participant_list"`
    - Add `group_id` string config (optional)
    - Add `project_name` string config (optional)
    - Make `input_file` input optional by adding `"optional": true`
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1_

  - [ ] 1.2 Create ProjectModeConfig Pydantic model in main.py
    - Define `ProjectModeConfig(BaseModel)` with fields: `group_id: str`, `project_name: str`, `modules: set[str]`, `info_paths: list[str]`, `study_id: str`
    - Add `field_validator` for `group_id` and `project_name` to reject blank/whitespace-only strings
    - Add `field_validator` for `modules` to filter to valid set `{UDS, FTLD, LBD}` and raise if none remain
    - _Requirements: 2.3, 2.4, 6.1, 6.4, 6.5_

  - [ ]* 1.3 Write property tests for ProjectModeConfig validation
    - **Property 2: Required string config rejection of blank values**
    - **Property 5: Module config parsing**
    - **Validates: Requirements 2.3, 2.4, 6.1, 6.4**

- [ ] 2. Implement run_project_mode orchestration in main.py
  - [ ] 2.1 Implement `run_project_mode` function in main.py
    - Accept `requests: list[DataRequestMatch]` and `gatherers: list[ModuleDataGatherer]`
    - Iterate all requests, apply each gatherer via `gather_request_data(request)`
    - Catch exceptions per subject-module combination, log warning with subject label and module name, continue
    - Return `True` when processing completes (even with individual failures)
    - _Requirements: 5.1, 5.3, 5.4, 8.1, 8.2, 8.3_

  - [ ] 2.2 Write property test for resilience of run_project_mode
    - **Property 4: All subjects processed with resilience**
    - **Validates: Requirements 4.2, 5.1, 5.3, 5.4, 8.2**

  - [ ]* 2.3 Write property test for per-subject-module warning logging
    - **Property 8: Per-subject-module warning for missing data**
    - **Validates: Requirements 8.1, 8.3**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement ProjectModeVisitor in run.py
  - [ ] 4.1 Implement `ProjectModeVisitor` class in run.py
    - Extend `GearExecutionEnvironment`
    - Constructor accepts `client`, `group_id`, `project_name`, `info_paths`, `modules`, `study_id`
    - Implement `create` classmethod: extract `group_id`, `project_name`, `modules`, `include_derived`, `study_id` from context config; validate with `ProjectModeConfig`; return visitor instance
    - _Requirements: 2.1, 2.2, 10.1_

  - [ ] 4.2 Implement `ProjectModeVisitor.run` method
    - Resolve group via `self.proxy` using `group_id`; fail with error log if not found
    - Resolve project within group by `project_name`; fail with error log if not found
    - Iterate `project.subjects.iter()` to get all subjects
    - Log warning and return early if zero subjects
    - Build `DataRequestMatch` per subject: `naccid=subject.label`, `subject_id=subject.id`, `project_label=project.label`
    - Create `ModuleDataGatherer` instances for each configured module
    - Call `run_project_mode(requests=..., gatherers=...)`
    - Write output CSV files using same `__write_output` pattern as existing visitor
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.2, 7.1, 7.2, 7.3, 10.1_

  - [ ]* 4.3 Write property test for subject-to-DataRequestMatch mapping
    - **Property 3: Subject-to-DataRequestMatch mapping correctness**
    - **Validates: Requirements 5.2**

- [ ] 5. Wire execution mode selection in entry point
  - [ ] 5.1 Update `main()` entry point in run.py for mode dispatch
    - Read `execution_mode` from context config with default `"participant_list"`
    - If `"project"`, run with `gear_type=ProjectModeVisitor`
    - If `"participant_list"`, run with `gear_type=GatherFormDataVisitor` (existing behavior)
    - If invalid value, log error with the invalid value and exit with failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 9.1_

  - [ ]* 5.2 Write property test for execution mode validation
    - **Property 1: Execution mode validation**
    - **Validates: Requirements 1.1, 1.4**

  - [ ] 5.3 Validate input_file requirement in participant_list mode
    - When `execution_mode` is `participant_list` and `input_file` is not provided, log error and exit with failure
    - When `execution_mode` is `project`, do not require `input_file`
    - _Requirements: 3.2, 3.3, 3.4, 9.4_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Output handling and filename generation
  - [ ] 7.1 Implement output file writing for project mode
    - Reuse the `__write_output` pattern from `GatherFormDataVisitor` in `ProjectModeVisitor`
    - Generate filenames as `{study_id}-{module_name}-{YYYY-MM-DD}.csv`
    - Skip writing for modules with no content, log warning identifying the module
    - Encode output as UTF-8
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 7.2 Write property test for output filename format
    - **Property 6: Output filename format**
    - **Validates: Requirements 6.3, 7.1**

  - [ ]* 7.3 Write property test for empty gatherers producing no output
    - **Property 7: Empty gatherers produce no output file**
    - **Validates: Requirements 7.2**

- [ ] 8. Integration tests and backward compatibility
  - [ ] 8.1 Write integration tests for project mode end-to-end
    - Mock Flywheel SDK (group resolution, project resolution, subject iteration)
    - Verify CSV output files are produced for modules with data
    - Verify error paths: group not found, project not found, empty project
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.1_

  - [ ] 8.2 Write backward compatibility tests for participant_list mode
    - Verify existing behavior unchanged when `execution_mode` is `participant_list` or unset
    - Verify `input_file` is still required in participant_list mode
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The actual Python module is `gather_form_data_app` (not `gather_form_data` as referenced in the design)
- `ModuleDataGatherer` and `DataRequestMatch` live in `common/src/python/data_requests/data_request.py`
- Test files should go in `gear/gather_form_data/test/python/` following the `_test` suffix convention

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "8.1", "8.2"] }
  ]
}
```
