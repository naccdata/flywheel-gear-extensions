# Implementation Plan: Gather Submission Status Performance

## Overview

Refactor `gather_submission_status` to reload QC log files concurrently using a `ThreadPoolExecutor`, replacing the sequential `ProjectReportVisitor.visit_project()` pattern. The clustering phase is unchanged; only the file-gathering phase is rewritten for concurrency.

## Tasks

- [x] 1. Add `reload_workers` config to manifest and update `run.py`
  - [x] 1.1 Add `reload_workers` config field to manifest.json
    - Edit `gear/gather_submission_status/src/docker/manifest.json`
    - Add `"reload_workers": {"description": "Number of concurrent threads for reloading QC file metadata", "type": "integer", "default": 10}` to the `config` section
    - _Requirements: 5.1_

  - [x] 1.2 Add `reload_workers` to `GatherSubmissionStatusVisitor` in `run.py`
    - Edit `gear/gather_submission_status/src/python/gather_submission_status_app/run.py`
    - Add `reload_workers: int` parameter to `__init__` and store as `self.__reload_workers`
    - In `create()`: read `reload_workers = int(options.get("reload_workers", 10))`, validate > 0 (raise `GearExecutionError` if not), pass to constructor
    - In `run()`: pass `reload_workers=self.__reload_workers` to `main.run()`
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 2. Rewrite `main.py` with concurrent file reloading
  - [x] 2.1 Rewrite `main.py` with concurrent reload orchestration
    - Replace contents of `gear/gather_submission_status/src/python/gather_submission_status_app/main.py`
    - New `run()` signature adds `reload_workers: int = 10` parameter
    - Add `_should_process_file(filename, matcher, ptid_set, modules)` helper that replicates `ProjectReportVisitor.__should_process_file` logic using `QC_FILENAME_PATTERN`
    - Add `_process_reloaded_file(file, adcid, file_visitor_builder, table_visitor)` helper that validates `file.info.qc`, calls `FileQCModel.model_validate(file.info, by_alias=True)`, creates visitor via factory, applies model, writes to table_visitor
    - Phase 1 (clustering): unchanged — `read_csv` + `clustering_visitor` with existing checks
    - Phase 2 (file gathering): create single `ThreadPoolExecutor(max_workers=reload_workers)` for entire run, iterate ADCID/project pairs, filter `project.project.files` with `_should_process_file`, submit `f.reload` futures, use `as_completed` to process results via `_process_reloaded_file`
    - Handle reload exceptions per-file (log warning, continue)
    - Remove `ProjectReportVisitor` import (no longer used)
    - Import `ThreadPoolExecutor` from `concurrent.futures`, `as_completed` from `concurrent.futures`, `FileQCModel` from `nacc_common.error_models`, `QCTransformerError` from `nacc_common.qc_report`, `ReportTableVisitor` from `nacc_common.qc_report`
    - Keep `QC_FILENAME_PATTERN` imported from `nacc_common.qc_report` (or define locally matching the same pattern)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 3.3, 3.4, 4.1, 6.2, 6.3_

- [x] 3. Write tests for the refactored gear
  - [x] 3.1 Write tests for `_should_process_file` filter equivalence
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/__init__.py`
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/conftest.py` with shared fixtures
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/test_file_filter.py`
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/BUILD` with `python_tests(name="tests")`
    - Test that filenames matching QC pattern with ptid in ptid_set and module in modules are accepted
    - Test that filenames not matching pattern are rejected
    - Test that filenames with ptid NOT in ptid_set are rejected
    - Test that filenames with module NOT in modules are rejected
    - Test case-insensitive module matching (e.g., "uds" in filename matches "UDS" in modules)
    - Use Hypothesis property-based testing: for any filename matching the QC pattern with ptid in ptid_set and module in modules, `_should_process_file` returns True
    - _Requirements: 6.3_ / _Property 1: Filter Equivalence_

  - [x] 3.2 Write tests for `_process_reloaded_file` processing logic
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/test_process_file.py`
    - Test that a file with valid `file.info.qc` produces expected report rows via the table_visitor
    - Test that a file without `file.info.qc` is skipped (logs warning, no rows written)
    - Test that a file with invalid QC data (ValidationError) is skipped (logs warning)
    - Test that a file causing QCTransformerError is skipped (logs error)
    - Test that file_visitor_builder is called with correct (file, adcid) arguments
    - Mock `FileEntry` with `.name`, `.info` attributes; mock `file_visitor_builder`; use `ListReportWriter` for assertions
    - _Requirements: 2.1, 2.2, 3.3, 6.2_ / _Property 4: QC Validation Equivalence_

  - [x] 3.3 Write integration test for end-to-end `main.run()` flow
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/test_main_integration.py`
    - Test happy path: CSV with valid rows, projects with matching QC files, correct output rows written to DictWriter
    - Test mixed path: some files reload successfully, one fails — successful files still processed, failed file logged
    - Test empty project (no matching files): no output rows, returns True
    - Test clustering failure (bad CSV): returns False, no file processing attempted
    - Mock `StatusRequestClusteringVisitor` (or use real one with mocked proxy), mock `project.project.files` with mock FileEntry objects, mock `file.reload()` to return pre-populated files
    - Verify `reload_workers` parameter is passed to ThreadPoolExecutor (can verify via mock or by testing with reload_workers=1 for deterministic ordering)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 4.1_ / _Property 3: Reload Failure Isolation_

  - [x] 3.4 Write test for `reload_workers` validation in `run.py`
    - Create `gear/gather_submission_status/test/python/gather_submission_status_test/test_config_validation.py`
    - Test that `reload_workers=0` raises `GearExecutionError`
    - Test that `reload_workers=-5` raises `GearExecutionError`
    - Test that `reload_workers=1` is accepted (valid minimum)
    - Mock `GearContext` with appropriate config options
    - _Requirements: 5.2_ / _Property 5: Non-Positive reload_workers Rejected_

- [x] 4. Final verification
  - [x] 4.1 Run full quality check
    - Run `full_quality_check` on all code to verify fix → lint → check → test pass
    - Address any issues found
    - _Requirements: all_

## Notes

- `ProjectReportVisitor` in nacc-common is NOT deleted or modified — other gears may still use it
- `QC_FILENAME_PATTERN` is already exported from `nacc_common.qc_report` — import it rather than duplicating the string
- `hypothesis>=6.0.0` is already in `requirements.txt`
- manifest.json changes are JSON-only — no Pants quality checks needed for task 1.1
- Subagents run targeted `pants_fix` + `pants_check` (source) or `pants_fix` + `pants_test` (tests) per subtask
- The `post-task-quality-check` hook runs `full_quality_check` at wave boundaries (parent task completion)
- The `tailor-on-file-create` hook runs `pants_tailor` when new `.py` files are created
- Test directories use `_test` suffix per project convention (`gather_submission_status_test/`)
- The existing `test/python/test_status_file.py` tests StatusRequest serialization and remains unchanged
- The existing `test/python/BUILD` file may need updating to include the new test subdirectory

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["4.1"] }
  ]
}
```
