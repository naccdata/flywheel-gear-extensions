# Requirements Document

> **Note**: This spec is finalized. The implementation renamed `lookback_hours` to `preceding_hours` and `LookbackConfig` to `TimeWindowConfig` after this spec was written. The source code is the authoritative reference for current naming. Do not modify code to match this document.

## Introduction

The pull-directory gear (v4.0.3) currently pulls all approved user records from the NACC REDCap directory on every run. This works well for the nightly full-pull schedule, but there is no way to perform incremental pulls that retrieve only records modified within a recent time window. The `REDCapProject.export_records()` method in `redcap_api` 0.1.5 supports `date_range_begin` and `date_range_end` parameters that filter records by last modification time. This feature adds an optional `lookback_hours` configuration argument to the pull-directory gear so that it can compute a relative time window (from `now - lookback_hours` to `now`) for time-scoped pulls, while maintaining full backward compatibility when no lookback window is specified.

## Glossary

- **Pull_Directory_Gear**: The Flywheel gear (`gear/pull_directory`) that retrieves user permission data from the NACC Directory REDCap project and converts it to a YAML file consumed by the user management gear.
- **DirectoryPullVisitor**: The gear execution visitor class in `gear/pull_directory/src/python/directory_app/run.py` that orchestrates the pull-directory gear lifecycle, including REDCap connection setup, record export, filtering, and output generation.
- **REDCapProject**: A class in the `redcap_api` package that provides `export_records()` for exporting records from a REDCap project with explicit field lists, date range filters, and other parameters.
- **Gear_Manifest**: The JSON configuration file (`gear/pull_directory/src/docker/manifest.json`) that defines the gear's metadata, inputs, and config options for the Flywheel platform.
- **Lookback_Hours**: An optional numeric configuration value that specifies how many hours into the past the gear should look when filtering records by last modification time. The gear computes the date range relative to the current run time.
- **GearExecutionError**: The standard error type raised by gears when a fatal configuration or execution error occurs, used to signal failures to the Flywheel platform.
- **Lookback_Config**: A Pydantic model that encapsulates the optional `lookback_hours` value and provides methods to compute the `date_range_begin` and `date_range_end` timestamps relative to the current time.

## Requirements

### Requirement 1: Add Optional Lookback Hours Configuration to Gear Manifest

**User Story:** As a platform administrator, I want to optionally specify a lookback window in hours when running the pull-directory gear, so that I can perform incremental pulls of recently modified records without computing dates manually.

#### Acceptance Criteria

1. THE Gear_Manifest SHALL include an optional `lookback_hours` config field of type number with a default value of 0.
2. THE Gear_Manifest SHALL describe the `lookback_hours` field as the number of hours to look back from the current time for filtering records by last modification time, where 0 means no filtering (full pull).

### Requirement 2: Validate Lookback Hours Configuration

**User Story:** As a platform administrator, I want the gear to validate my lookback hours input, so that misconfigured values are caught before the gear attempts to pull records.

#### Acceptance Criteria

1. WHEN a `lookback_hours` value is provided, THE Pull_Directory_Gear SHALL validate that the value is a positive number.
2. IF `lookback_hours` is a negative number, THEN THE Pull_Directory_Gear SHALL raise a GearExecutionError with a message indicating that lookback_hours must be a positive number.

### Requirement 3: Compute and Pass Date Range to REDCap Export

**User Story:** As a platform administrator, I want the gear to compute a date range from my specified lookback window and use it when querying REDCap, so that only records modified within that window are returned.

#### Acceptance Criteria

1. WHEN `lookback_hours` is greater than 0, THE DirectoryPullVisitor SHALL compute `date_range_begin` as the current time minus `lookback_hours` hours, formatted as `YYYY-MM-DD HH:MM:SS`.
2. WHEN `lookback_hours` is greater than 0, THE DirectoryPullVisitor SHALL compute `date_range_end` as the current time, formatted as `YYYY-MM-DD HH:MM:SS`.
3. WHEN `lookback_hours` is greater than 0, THE DirectoryPullVisitor SHALL pass the computed `date_range_begin` and `date_range_end` values to `REDCapProject.export_records()`.
4. WHEN `lookback_hours` is 0 or not provided, THE DirectoryPullVisitor SHALL call `export_records()` without `date_range_begin` or `date_range_end` parameters.

### Requirement 4: Maintain Backward Compatibility

**User Story:** As a platform administrator, I want the gear to behave exactly as before when no lookback window is specified, so that existing nightly full-pull schedules continue to work without modification.

#### Acceptance Criteria

1. WHEN `lookback_hours` is 0 or not provided in the gear configuration, THE Pull_Directory_Gear SHALL export all records from REDCap with no date filtering applied.
2. THE Pull_Directory_Gear SHALL continue to filter exported records by `permissions_approval` regardless of whether a lookback window is specified.
3. THE Pull_Directory_Gear SHALL produce the same YAML output format regardless of whether a lookback window is specified.
4. THE Pull_Directory_Gear SHALL continue to use the existing `dry_run`, `user_file`, `parameter_path`, and `notifications_path` config options without modification.

### Requirement 5: Create Pydantic Configuration Model for Lookback Window

**User Story:** As a developer, I want the lookback configuration to be encapsulated in a Pydantic model, so that validation is centralized and the pattern is consistent with other gears in the codebase.

#### Acceptance Criteria

1. THE Pull_Directory_Gear SHALL define a Pydantic configuration model that includes an optional `lookback_hours` numeric field with a default of 0.
2. THE configuration model SHALL validate that `lookback_hours` is not negative using a Pydantic field validator.
3. THE configuration model SHALL provide a method that accepts the current time and returns the computed `date_range_begin` and `date_range_end` strings when `lookback_hours` is greater than 0, or None when `lookback_hours` is 0.

### Requirement 6: Log Lookback Window Usage

**User Story:** As a platform administrator, I want the gear to log whether a lookback window is being applied, so that I can verify the gear is running in the expected mode (full pull vs. incremental pull).

#### Acceptance Criteria

1. WHEN `lookback_hours` is greater than 0, THE Pull_Directory_Gear SHALL log a message indicating the lookback window being used, including the `lookback_hours` value and the computed date range.
2. WHEN `lookback_hours` is 0 or not provided, THE Pull_Directory_Gear SHALL log a message indicating that all records are being pulled without date filtering.
