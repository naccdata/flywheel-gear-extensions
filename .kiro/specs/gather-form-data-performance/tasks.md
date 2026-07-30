# Implementation Plan: Gather Form Data Performance

## Overview

Refactor `gather_form_data` from sequential per-NACCID processing to a two-phase batch approach: batch-resolve NACCIDs via OR-list queries, then call `gather_project_data` with the resolved subject IDs. This leverages the proven batched + concurrent pattern from `center_form_export`.

## Tasks

- [x] 1. Add `find_subjects_by_labels` to FlywheelProxy and update manifest config
  - [x] 1.1 Add `find_subjects_by_labels` method to `FlywheelProxy`
    - Add method to `common/src/python/flywheel_adaptor/flywheel_proxy.py`
    - Signature: `find_subjects_by_labels(self, labels: list[str], project_id: str, batch_size: int = 100) -> list[Subject]`
    - Batch labels into groups of `batch_size`, issue one `subjects.find(f"label=|[{','.join(batch)}],parents.project={project_id}")` per batch
    - Return flat list of all matched Subject objects
    - _Requirements: 1.2_

  - [x] 1.2 Add `batch_size` and `reload_workers` config fields to manifest.json
    - Add to `gear/gather_form_data/src/docker/manifest.json`
    - `batch_size`: type "integer", default 100, description about OR-list query batch size
    - `reload_workers`: type "integer", default 10, description about concurrent reload threads
    - _Requirements: 3.1, 3.2_

- [x] 2. Rewrite gear source code for two-phase batch processing
  - [x] 2.1 Rewrite `main.py` with two-phase batch logic
    - Replace contents of `gear/gather_form_data/src/python/gather_form_data_app/main.py`
    - New `run()` signature returns `tuple[bool, list[ModuleDataGatherer]]`
    - Parameters: `request_file`, `proxy`, `study_id`, `project_names`, `modules`, `info_paths`, `error_writer`, `batch_size`, `reload_workers`, `formver_split`
    - Phase 1: Read CSV with `DictReader`, validate each row with `DataRequest.model_validate`, collect valid NACCIDs and line numbers, report validation errors
    - Look up project IDs using `proxy.find_projects_with_pattern(...)` + `create_project_matcher`
    - Batch resolve NACCIDs via `proxy.find_subjects_by_labels(deduplicated_naccids, project_id, batch_size)` for each project
    - Diff resolved labels vs requested to produce "no-participant" errors with correct line numbers
    - Phase 2: Create `ModuleDataGatherer` per module, call `gather_project_data(subject_ids, batch_size, reload_workers)` on each
    - Return `(success, gatherers)` where success is False if any errors occurred
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 5.1, 5.2, 6.1, 6.3_

  - [x] 2.2 Update `GatherFormDataVisitor` in `run.py` to use new `main.run()` signature
    - Update `gear/gather_form_data/src/python/gather_form_data_app/run.py`
    - Add `batch_size` and `reload_workers` to `__init__` and `create()` (read from `options`)
    - Add config validation: raise `GearExecutionError` if either value is non-positive
    - Replace the `DataRequestVisitor`-based call in `run()` with direct call to new `main.run()`
    - Pass `proxy`, `study_id`, `project_names`, `modules`, `info_paths`, `error_writer`, `batch_size`, `reload_workers`, `formver_split`
    - Use returned `(success, data_gatherers)` for output writing (unchanged `_write_module_output` call)
    - Keep QC metadata and file tagging logic unchanged
    - Remove `DataRequestVisitor` import (no longer used by this file)
    - _Requirements: 2.4, 3.3, 3.4, 5.2, 5.3, 6.2_

- [x] 3. Checkpoint - Ensure source changes are consistent
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Write tests
  - [x] 4.1 Write property tests for NACCID validation and batch resolution
    - Create `gear/gather_form_data/test/python/gather_form_data_test/__init__.py`
    - Create `gear/gather_form_data/test/python/gather_form_data_test/conftest.py` with shared fixtures
    - Create `gear/gather_form_data/test/python/gather_form_data_test/test_main_properties.py`
    - Create `gear/gather_form_data/test/python/gather_form_data_test/BUILD`
    - Use Hypothesis with `@settings(max_examples=100)`
    - **Property 1: NACCID validation separates valid from invalid**
    - **Validates: Requirements 1.1**
    - **Property 3: Error attribution completeness**
    - **Validates: Requirements 1.3, 5.1**
    - **Property 5: Non-positive config parameters rejected**
    - **Validates: Requirements 3.3, 3.4**
    - _Requirements: 1.1, 1.3, 3.3, 3.4, 5.1_

  - [x] 4.2 Write property tests for `find_subjects_by_labels` batching
    - Create `common/test/python/flywheel_adaptor_test/__init__.py`
    - Create `common/test/python/flywheel_adaptor_test/test_find_subjects_properties.py`
    - Create `common/test/python/flywheel_adaptor_test/BUILD`
    - Mock `self.__fw.subjects.find` to record calls
    - Use Hypothesis with `@settings(max_examples=100)`
    - **Property 2: Batching correctness — for N labels and batch_size B, exactly ceil(N/B) queries issued, each with at most B labels**
    - **Validates: Requirements 1.2**
    - **Property 4: Resolution preserves multiplicity — NACCID matching K projects produces K subject IDs**
    - **Validates: Requirements 1.4**
    - _Requirements: 1.2, 1.4_

  - [x] 4.3 Write integration test for end-to-end gear flow
    - Create `gear/gather_form_data/test/python/gather_form_data_test/test_main_integration.py`
    - Test happy path: all NACCIDs resolve, correct gatherers populated
    - Test mixed path: some resolve, some don't, correct error count and QC state
    - Test empty CSV: no errors, no output
    - Test all-invalid CSV: all errors, success=False
    - Mock `FlywheelProxy` methods (`find_projects_with_pattern`, `find_subjects_by_labels`)
    - Mock `ModuleDataGatherer.gather_project_data` to verify called with correct subject IDs and parameters
    - _Requirements: 2.1, 4.1, 4.3, 5.2, 6.1_

- [x] 5. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `DataRequestVisitor` in `data_request.py` is NOT deleted — other callers may still use it
- `FlywheelProxy.find_projects_with_pattern(pattern)` already exists
- `hypothesis>=6.0.0` is already in `requirements.txt`
- manifest.json changes are JSON-only — no Pants quality checks needed for task 1.2
- Subagents run targeted `pants_fix` + `pants_check` (source) or `pants_fix` + `pants_test` (tests) per subtask
- The `post-task-quality-check` hook runs `full_quality_check` at wave boundaries (parent task completion)
- The `tailor-on-file-create` hook runs `pants_tailor` when new `.py` files are created
- Test directories use `_test` suffix per project convention (`gather_form_data_test/`, `flywheel_adaptor_test/`)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["4.1", "4.2", "4.3"] }
  ]
}
```
