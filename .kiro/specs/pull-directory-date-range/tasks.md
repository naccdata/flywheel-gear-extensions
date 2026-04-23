# Implementation Plan: Pull Directory Date Range

> **Note**: This spec is finalized. The implementation renamed `lookback_hours` to `preceding_hours` and `LookbackConfig` to `TimeWindowConfig` after this spec was written. The source code is the authoritative reference for current naming. Do not modify code to match this document.

## Overview

Add an optional `lookback_hours` configuration parameter to the pull-directory gear, enabling incremental pulls of recently modified records from REDCap. Implementation creates a new `LookbackConfig` Pydantic model, updates the gear manifest, and modifies `DirectoryPullVisitor.create()` to compute and pass date ranges to `export_records()`.

## Tasks

- [x] 1. Create LookbackConfig Pydantic model
  - [x] 1.1 Create `gear/pull_directory/src/python/directory_app/config.py` with `LookbackConfig` model
    - Define `LookbackConfig(BaseModel)` with `lookback_hours: float` field (default 0)
    - Add `@field_validator("lookback_hours")` that raises `ValidationError` for negative values
    - Implement `get_date_range(now: Optional[datetime] = None) -> Optional[Tuple[str, str]]` method
    - When `lookback_hours > 0`: return `(begin_str, end_str)` formatted as `"YYYY-MM-DD HH:MM:SS"`
    - When `lookback_hours == 0`: return `None`
    - Add a `BUILD` entry or update existing BUILD file for the new source file
    - _Requirements: 2.1, 2.2, 5.1, 5.2, 5.3_

  - [x] 1.2 Write property test: non-negative validation (Property 1)
    - Create `gear/pull_directory/test/python/test_lookback_config.py`
    - **Property 1: Non-negative validation accepts if and only if non-negative**
    - Use Hypothesis to generate random floats; non-negative values construct successfully, negative values raise `ValidationError`
    - Tag: Feature: pull-directory-date-range, Property 1
    - **Validates: Requirements 2.1, 2.2, 5.2**

  - [x] 1.3 Write property test: date range computation correctness (Property 2)
    - Add to `gear/pull_directory/test/python/test_lookback_config.py`
    - **Property 2: Date range computation correctness**
    - Use Hypothesis to generate positive floats for `lookback_hours` and arbitrary datetimes for `now`
    - Verify returned tuple matches `(now - timedelta(hours=value)).strftime("%Y-%m-%d %H:%M:%S")` and `now.strftime("%Y-%m-%d %H:%M:%S")`
    - Verify `lookback_hours=0` returns `None`
    - Tag: Feature: pull-directory-date-range, Property 2
    - **Validates: Requirements 3.1, 3.2, 5.3**

- [x] 2. Update gear manifest with lookback_hours config field
  - [x] 2.1 Add `lookback_hours` field to `gear/pull_directory/src/docker/manifest.json`
    - Add to the `config` object: `"lookback_hours": { "description": "Number of hours to look back from the current time for filtering records by last modification time. 0 means no filtering (full pull).", "type": "number", "default": 0 }`
    - _Requirements: 1.1, 1.2_

- [x] 3. Update DirectoryPullVisitor.create() to use LookbackConfig and pass date range
  - [x] 3.1 Modify `gear/pull_directory/src/python/directory_app/run.py` to integrate LookbackConfig
    - Import `LookbackConfig` from `directory_app.config` and `ValidationError` from `pydantic`
    - In `create()`, read `lookback_hours` from `context.config.opts` (default 0) and construct `LookbackConfig`
    - Catch `ValidationError` from `LookbackConfig` construction and wrap in `GearExecutionError`
    - Call `config.get_date_range()` to get the optional date range tuple
    - When date range is present, pass `date_range_begin` and `date_range_end` kwargs to `project.export_records()`
    - When date range is `None`, call `export_records()` with only `fields` (existing behavior)
    - Add logging: log lookback window and computed date range when `lookback_hours > 0`; log "pulling all records" when `lookback_hours == 0`
    - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 6.1, 6.2_

  - [x] 3.2 Write unit tests for date range passing in DirectoryPullVisitor.create()
    - Add tests to `gear/pull_directory/test/python/test_directory_pull_visitor_create.py`
    - Test: `export_records` called with `date_range_begin` and `date_range_end` when `lookback_hours > 0`
    - Test: `export_records` called without date range kwargs when `lookback_hours == 0`
    - Test: `filter_approved_records` is still called regardless of lookback setting
    - Test: negative `lookback_hours` raises `GearExecutionError`
    - Test: default config (no `lookback_hours` key) behaves as full pull
    - Update `conftest.py` `MockGearContext` if needed to support `lookback_hours` in config opts
    - _Requirements: 2.2, 3.3, 3.4, 4.1, 4.2, 4.4_

  - [x] 3.3 Write unit tests for logging behavior
    - Add tests to `gear/pull_directory/test/python/test_directory_pull_visitor_create.py`
    - Test: log message includes lookback_hours value and computed date range when `lookback_hours > 0`
    - Test: log message indicates full pull with no date filtering when `lookback_hours == 0`
    - _Requirements: 6.1, 6.2_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing codebase
