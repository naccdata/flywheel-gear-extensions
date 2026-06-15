# Implementation Plan: Pipeline Event Logger

## Overview

Implement the Pipeline Event Logger gear following the standard NACC gear architecture. The gear reads QC outcomes from upstream gears via `file.info.qc.{upstream_gear_name}`, updates the project-level QC status log (attributed to the upstream gear), and optionally captures a `VisitEvent` to S3. The implementation follows the `image_identifier_lookup` gear as a reference pattern, with `run.py` handling Flywheel context and `main.py` containing business logic.

## Tasks

- [x] 1. Scaffold gear directory structure and build configuration
  - [x] 1.1 Create gear directory structure and boilerplate files
    - Create `gear/pipeline_event_logger/src/docker/` with `Dockerfile`, `manifest.json`, `BUILD`, `.gitignore`
    - Create `gear/pipeline_event_logger/src/python/pipeline_event_logger_app/` with `__init__.py`, `BUILD`
    - Create `gear/pipeline_event_logger/test/python/pipeline_event_logger_test/` with `__init__.py`, `BUILD`, `conftest.py`
    - `manifest.json` must define inputs (`api-key`, `input_file`) and config (`upstream_gear_name`, `event_actions`, `event_environment`, `event_bucket`, `apikey_path_prefix`, `dry_run`) per the design
    - `Dockerfile` follows the standard pattern: Python 3.12 base, copy manifest and pex binary, set entrypoint
    - `BUILD` for docker defines `file(name="manifest")` and `docker_image()` with dependencies on the app `bin` target
    - `BUILD` for app defines `python_sources()` and `pex_binary(name="bin", entry_point="run.py")`
    - `BUILD` for tests defines `python_tests(name="tests")`
    - _Requirements: 7.1, 7.4_

- [x] 2. Implement `run.py` — `PipelineEventLoggerVisitor`
  - [x] 2.1 Implement `PipelineEventLoggerVisitor` class with `create()` and `run()`
    - Extend `GearExecutionEnvironment` following the `ImageIdentifierLookupVisitor` pattern
    - `create()`: initialize `GearBotClient` from context and parameter store, create `InputFileWrapper` for `input_file`, read config params (`upstream_gear_name`, `apikey_path_prefix`), read optional config (`event_actions`, `event_environment`, `event_bucket`, `dry_run`), parse `event_actions` as `dict[str, str]`, conditionally initialize `VisitEventCapture` with `S3BucketInterface.create_from_environment(event_bucket)` when event capture is configured, raise `GearExecutionError` if `event_actions` is non-empty but `event_environment` or `event_bucket` is missing
    - `run()`: retrieve input file via `proxy.get_file(file_input.file_id)`, retrieve parent project via `proxy.get_project_by_id(file.parents.project)`, wrap project as `ProjectAdaptor`, delegate to `PipelineEventLogger(...).run()`
    - Add `main()` entry point using `GearEngine.create_with_parameter_store().run()`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.2, 7.3, 7.4, 8.1, 8.2_

- [x] 3. Implement `main.py` — `PipelineEventLogger` business logic
  - [x] 3.1 Implement `PipelineEventLogger` class with `__init__()` and `run()` orchestration
    - Constructor accepts `file_entry`, `project`, `upstream_gear_name`, `event_capture` (Optional), `event_actions` (dict)
    - `run()` orchestrates the workflow: `_read_qc_metadata()` → `_read_data_identification()` → `_resolve_timestamp()` → `_update_qc_status_log()` (non-critical) → `_capture_event()` (non-critical)
    - _Requirements: 7.2, 7.3_

  - [x] 3.2 Implement `_read_qc_metadata()` — extract QC status and errors
    - Reload file entry to get fresh metadata
    - Validate `file.info.qc` exists, raise `GearExecutionError` if missing
    - Parse with `FileQCModel.model_validate(file_entry.info)`, raise `GearExecutionError` on `ValidationError`
    - Look up `upstream_gear_name` in the model, raise `GearExecutionError` if not found
    - Extract and return `(qc_status, FileErrorList(errors=errors))`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.5_

  - [x] 3.3 Implement `_read_data_identification()` — read from `file.info.data_identification`
    - Check `file_entry.info.get("data_identification")` exists, raise `GearExecutionError` if missing
    - Deserialize via `DataIdentification.from_visit_metadata(**data_identification_dict)`
    - Raise `GearExecutionError` on `ValidationError` or `ValueError`
    - _Requirements: 2.1, 2.2, 2.3, 8.5_

  - [x] 3.4 Implement `_resolve_timestamp()` — prefer `validated-timestamp` over `file.modified`
    - Check `file_entry.info.get("validated-timestamp")`
    - If present, parse with `datetime.strptime(ts, DEFAULT_DATE_TIME_FORMAT)`
    - If absent, fall back to `file_entry.modified`
    - _Requirements: 5.1, 5.2_

  - [x] 3.5 Implement `_update_qc_status_log()` — non-critical QC log update
    - Create `ErrorLogTemplate()`, `FileVisitAnnotator(project=self._project)`, `QCStatusLogManager(error_log_template, visit_annotator)`
    - Call `qc_log_manager.update_qc_log()` with `gear_name=self._upstream_gear_name` (not `"pipeline-event-logger"`)
    - Wrap in try/except, log warning on failure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 8.4_

  - [x] 3.6 Implement `_capture_event()` — non-critical event capture to S3
    - Return immediately if `self._event_capture is None`
    - Normalize QC status to outcome key: `"PASS"` → `"pass"`, `"FAIL"` → `"fail"`, `"IN REVIEW"` → `"in-review"`
    - Look up outcome key in `self._event_actions`, skip if not found
    - Call `create_visit_event()` with `action=event_action`, `gear_name=self._upstream_gear_name`
    - Call `self._event_capture.capture_event(visit_event)` if event created
    - Wrap in try/except, log warning on failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 3.3, 8.4_

- [x] 4. Checkpoint — Verify gear scaffolding and core logic
  - Ensure all source files are syntactically valid and BUILD targets resolve
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Write unit tests for `PipelineEventLogger` business logic
  - [x] 5.1 Create test fixtures in `conftest.py`
    - Factory for mock `FileEntry` with configurable `info` dict (qc metadata, data_identification, validated-timestamp)
    - Factory for mock `ProjectAdaptor` with configurable label and group
    - Mock `QCStatusLogManager` and `VisitEventCapture`
    - _Requirements: 7.1_

  - [x] 5.2 Write unit tests for `_read_qc_metadata()` in `test_main.py`
    - Test valid QC extraction returns correct status and errors
    - Test missing `file.info.qc` raises `GearExecutionError`
    - Test missing `file.info.qc.{upstream_gear_name}` raises `GearExecutionError`
    - Test invalid QC structure raises `GearExecutionError`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 5.3 Write unit tests for `_read_data_identification()` in `test_main.py`
    - Test valid `data_identification` in `file.info` returns correct `DataIdentification`
    - Test missing `data_identification` raises `GearExecutionError`
    - Test invalid `data_identification` raises `GearExecutionError`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 5.4 Write unit tests for `_resolve_timestamp()` in `test_main.py`
    - Test `validated-timestamp` present returns parsed timestamp
    - Test `validated-timestamp` absent falls back to `file.modified`
    - _Requirements: 5.1, 5.2_

  - [x] 5.5 Write unit tests for `_update_qc_status_log()` in `test_main.py`
    - Test correct parameters passed to `QCStatusLogManager.update_qc_log` (upstream gear name attribution)
    - Test failure is non-critical (logs warning, does not raise)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 8.4_

  - [x] 5.6 Write unit tests for `_capture_event()` in `test_main.py`
    - Test correct event action selected per QC outcome from `event_actions` mapping
    - Test skip when no matching key in `event_actions`
    - Test skip when `event_capture` is `None`
    - Test failure is non-critical (logs warning, does not raise)
    - Test upstream gear name used in event (not `"pipeline-event-logger"`)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 3.3_

  - [x] 5.7 Write unit tests for `PipelineEventLoggerVisitor.create()` configuration validation in `test_run.py`
    - Test `event_actions` non-empty without `event_environment` raises `GearExecutionError`
    - Test `event_actions` non-empty without `event_bucket` raises `GearExecutionError`
    - Test empty `event_actions` results in `event_capture = None`
    - _Requirements: 6.3, 8.1_

- [x] 6. Checkpoint — Ensure all unit tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x]* 7. Write property-based tests with Hypothesis
  - [x]* 7.1 Write property test for upstream gear name attribution
    - **Property 1: Upstream gear name attribution**
    - For any valid upstream gear name, verify `gear_name` passed to `QCStatusLogManager.update_qc_log` equals the upstream gear name, never `"pipeline-event-logger"`
    - Use Hypothesis `st.text()` strategy for gear name generation
    - **Validates: Requirements 3.3**

  - [x]* 7.2 Write property test for event action selection by QC outcome
    - **Property 2: Event action selected by QC outcome**
    - For any valid combination of QC status and `event_actions` mapping, verify the captured event's action matches the mapped value, and `gear_name` equals the upstream gear name. If the outcome key is absent from `event_actions`, verify no event is captured.
    - Use Hypothesis strategies for QC status (`st.sampled_from`) and event_actions dict (`st.dictionaries`)
    - **Validates: Requirements 4.1, 4.2, 4.4, 3.3**

  - [x]* 7.3 Write property test for timestamp resolution
    - **Property 3: Timestamp resolution prefers validated-timestamp**
    - For any file entry, if `validated-timestamp` is present and parseable, the resolved timestamp equals the parsed value. If absent, it equals `file.modified`.
    - Use Hypothesis `st.datetimes()` strategy for timestamp generation
    - **Validates: Requirements 5.1, 5.2**

  - [x]* 7.4 Write property test for QC metadata extraction round-trip
    - **Property 4: QC metadata extraction round-trip**
    - For any valid `FileQCModel` containing a gear entry, extracting QC status and errors via `_read_qc_metadata` returns the same status and errors stored in the model
    - Use Hypothesis strategies for QC status and error lists
    - **Validates: Requirements 1.1, 1.2**

- [x] 8. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses Python throughout — no language selection needed
- The gear follows the `image_identifier_lookup` pattern for QC logging and event capture
