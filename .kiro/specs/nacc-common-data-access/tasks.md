# Implementation Plan: NACC Common Data Access

## Overview

Extend `nacc-common`'s public API in `error_data.py` with submission-oriented data access functions. The implementation adds an optional `ptids` parameter to existing functions, introduces two private helpers (`_find_submission`, `_should_include_file`), and four new public functions (`get_submission_qc_summary`, `get_submission_errors`, `get_submission_visit_metadata`, `list_submissions`). All new functions return plain dicts and follow the established patterns in the module.

## Tasks

- [x] 1. Add private helpers and PTID filtering to existing functions
  - [x] 1.1 Add new imports and implement `_find_submission` and `_should_include_file` in `error_data.py`
    - Add imports: `re`, `logging`, `FileEntry` from flywheel, `FileQCModel` from `error_models`, `DataIdentification` from `data_identification`, `QC_FILENAME_PATTERN` and `extract_visit_keys` from `qc_report`, `ValidationError` from pydantic
    - Implement `_find_submission(project, identifier) -> Optional[FileEntry]` — iterates `project.files`, matches by `.name`, calls `file.reload()`, returns `FileEntry` or `None`
    - Implement `_should_include_file(filename, modules=None, ptids=None) -> bool` — matches filename against `QC_FILENAME_PATTERN`, applies PTID and module filters
    - _Requirements: 3.4, 4.3, 5.2, 6.1, 6.2_
  - [x] 1.2 Add optional `ptids` parameter to `get_error_data` and `get_status_data`
    - Add `ptids: Optional[set[str]] = None` parameter to both function signatures
    - Pass `ptids` as `ptid_set` to `ProjectReportVisitor` constructor in both functions
    - Existing calls without `ptids` must continue working identically
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 7.1, 7.2_
  - [x] 1.3 Write example tests for PTID filtering on `get_error_data` and `get_status_data`
    - Create `nacc-common/test/python/test_error_data_ptid_filter.py`
    - Test: calling with `ptids` filters results to matching PTIDs only
    - Test: calling without `ptids` returns all results (backward compatibility)
    - Test: calling with both `modules` and `ptids` applies both filters
    - Mock `Project` with `.files` list of mock `FileEntry` objects, `.info` with `pipeline_adcid`
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 7.1, 7.2_

- [x] 2. Implement per-submission QC summary function
  - [x] 2.1 Implement `get_submission_qc_summary` in `error_data.py`
    - Signature: `get_submission_qc_summary(project: Project, identifier: str) -> Optional[dict[str, Any]]`
    - Use `_find_submission` to resolve identifier to `FileEntry`
    - Build `FileQCModel.create(file_entry)`; return `None` if `qc` dict is empty or `ValidationError` is raised
    - Return dict with `"identifier"`, `"overall_status"` (from `get_file_status()`), and `"stages"` mapping each gear name to `{"status": gear_model.get_status(), "error_count": len(gear_model.get_errors())}`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 2.2 Write property test for QC summary (Property 1)
    - Create `nacc-common/test/python/test_submission_qc_summary.py`
    - **Property 1: QC summary faithfully represents FileQCModel**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Use Hypothesis to generate `FileQCModel` instances with random gear names, statuses, and error lists
    - Assert: `"identifier"` matches input, `"overall_status"` matches `get_file_status()`, `"stages"` has entry for every gear with correct status and error count
  - [ ]* 2.3 Write example tests for QC summary edge cases
    - Test: returns `None` when identifier doesn't resolve (file not found)
    - Test: returns `None` when submission has empty `qc` dict
    - Test: returns `None` when `FileQCModel.create()` raises `ValidationError`
    - _Requirements: 3.4, 3.5, 3.6_

- [x] 3. Implement per-submission error details function
  - [x] 3.1 Implement `get_submission_errors` in `error_data.py`
    - Signature: `get_submission_errors(project: Project, identifier: str) -> list[dict[str, Any]]`
    - Use `_find_submission` to resolve identifier; return `[]` if not found
    - Build `FileQCModel.create(file_entry)`; return `[]` on `ValidationError`
    - Iterate all gears, collect errors via `gear_model.get_errors()`, serialize each `FileError` with `model_dump(by_alias=True)` and add `"stage"` key
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - [ ]* 3.2 Write property test for error details (Property 2)
    - Add to `nacc-common/test/python/test_submission_errors.py`
    - **Property 2: Error details faithfully represent FileQCModel errors**
    - **Validates: Requirements 4.1, 4.2, 4.5**
    - Use Hypothesis to generate `FileQCModel` instances with errors across multiple gears
    - Assert: total dicts equals sum of `len(gear_model.get_errors())`, each dict has `"stage"` matching gear name and is a superset of `FileError.model_dump(by_alias=True)`
  - [ ]* 3.3 Write example tests for error details edge cases
    - Test: returns `[]` when identifier doesn't resolve
    - Test: returns `[]` when submission has no errors
    - Test: error dicts include `"stage"` key plus all `FileError` fields serialized with `by_alias=True`
    - _Requirements: 4.3, 4.4, 4.6_

- [x] 4. Implement per-submission visit metadata function
  - [x] 4.1 Implement `get_submission_visit_metadata` in `error_data.py`
    - Signature: `get_submission_visit_metadata(project: Project, identifier: str) -> Optional[dict[str, Any]]`
    - Use `_find_submission` to resolve identifier; return `None` if not found
    - Call `DataIdentification.from_visit_info(file_entry)`; return `None` if result is `None`
    - Return `data_id.model_dump()`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [ ]* 4.2 Write property test for visit metadata (Property 3)
    - Create `nacc-common/test/python/test_submission_visit_metadata.py`
    - **Property 3: Visit metadata round trip**
    - **Validates: Requirements 5.1**
    - Use Hypothesis to generate visit metadata dicts, mock `FileEntry` with matching `.info.visit` data
    - Assert: returned dict equals `DataIdentification.from_visit_info(file_entry).model_dump()`
  - [ ]* 4.3 Write example tests for visit metadata edge cases
    - Test: returns `None` when identifier doesn't resolve
    - Test: returns `None` when submission has no visit metadata
    - Test: returned dict is a plain dict, not a Pydantic model
    - _Requirements: 5.2, 5.3, 5.4_

- [x] 5. Implement submission listing function
  - [x] 5.1 Implement `list_submissions` in `error_data.py`
    - Signature: `list_submissions(project: Project, modules=None, ptids=None) -> list[dict[str, Any]]`
    - Iterate `project.files`, filter with `_should_include_file`
    - For each matching file, extract PTID, date, module from filename via `extract_visit_keys`
    - Attempt `FileQCModel.create()` for `overall_status`; set to `None` on failure
    - Return list of dicts with `"identifier"`, `"ptid"`, `"date"`, `"module"`, `"overall_status"`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_
  - [x] 5.2 Write property test for submission listing filters (Property 4)
    - Create `nacc-common/test/python/test_list_submissions.py`
    - **Property 4: Submission listing filter correctness**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    - Use Hypothesis to generate sets of QC log filenames and filter combinations
    - Assert: every result dict has `"ptid"` in `ptids` set (when provided) and `"module"` in `modules` set (case-insensitive, when provided)
  - [ ]* 5.3 Write property test for submission listing output structure (Property 5)
    - Add to `nacc-common/test/python/test_list_submissions.py`
    - **Property 5: Submission listing output structure matches identifier**
    - **Validates: Requirements 6.5, 6.6**
    - Assert: each dict has `"identifier"`, `"ptid"`, `"date"`, `"module"` matching regex capture groups, and `"overall_status"` matching `FileQCModel.get_file_status()` or `None`
  - [ ]* 5.4 Write example tests for submission listing edge cases
    - Test: returns `[]` when project has no QC log files
    - Test: filters by modules only, ptids only, and both together
    - Test: gracefully handles individual `ValidationError` by setting `overall_status` to `None`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.7_

- [x] 6. JSON serialization property test and BUILD configuration
  - [ ]* 6.1 Write property test for JSON serialization contract (Property 6)
    - Create `nacc-common/test/python/test_json_serializable.py`
    - **Property 6: All return values are JSON-serializable plain dicts**
    - **Validates: Requirements 8.1, 8.2, 8.3**
    - Use Hypothesis to generate inputs for each public function, assert `json.dumps()` succeeds without custom encoders, assert no `BaseModel` instances or Flywheel objects in results
  - [x] 6.2 Update `nacc-common/test/python/BUILD` to add `hypothesis` as a test dependency
    - Add `dependencies=["3rdparty/python#hypothesis"]` to the `python_tests` target (or add to `requirements.txt` if needed)
    - Verify the existing Hypothesis-based test (`test_property_visit_metadata.py`) pattern for dependency resolution
    - _Requirements: all property tests depend on this_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All functions are implemented in the single file `error_data.py` to keep the public API in one module
- No checkpoint tasks are included — project hooks enforce quality checks automatically
