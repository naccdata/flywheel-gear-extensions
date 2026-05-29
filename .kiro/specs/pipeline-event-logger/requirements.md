# Requirements Document

## Introduction

The Pipeline Event Logger is an independent Flywheel gear that bridges the gap between upstream pipeline gears (which write QC results to file metadata via `context.metadata.add_qc_result`) and NACC's project-level QC status logging and S3 event capture systems. It runs after an upstream gear completes, reads the QC outcome from the file's custom info, updates the project-level QC status log attributing the entry to the upstream gear, and optionally captures a `VisitEvent` to the S3 transaction log.

This gear is needed for the imaging pipeline, where preexisting Flywheel gears process files and write QC results but have no knowledge of NACC's QC status logs or event capture infrastructure.

## Glossary

- **Pipeline_Event_Logger**: The Flywheel gear being specified. It reads QC results written by upstream gears and propagates them to NACC's QC status log and event capture systems.
- **Upstream_Gear**: A Flywheel gear that runs before the Pipeline_Event_Logger and writes QC results to `file.info.qc.{gear_name}` using the Flywheel QC metadata convention (`context.metadata.add_qc_result`).
- **QC_Status_Log**: A project-level file managed by `QCStatusLogManager` that records timestamped QC status entries for each visit/file, keyed by gear name.
- **VisitEvent**: A Pydantic model representing a pipeline event (e.g., "submit", "pass-qc") captured to the S3 transaction log via `VisitEventCapture`.
- **FileQCModel**: A Pydantic model (`nacc_common.error_models.FileQCModel`) that represents the QC metadata structure at `file.info.qc`, containing per-gear validation results.
- **GearQCModel**: A Pydantic model (`nacc_common.error_models.GearQCModel`) nested within `FileQCModel` that holds the validation state and error list for a single gear.
- **DataIdentification**: A Pydantic model (`nacc_common.data_identification.DataIdentification`) that identifies a visit/file by participant, date, visit number, and data type (form module or imaging modality). Used to generate QC log filenames and create events.
- **QCStatusLogManager**: A class in `common/src/python/error_logging/qc_status_log_creator.py` that manages creation and update of project-level QC status log files.
- **VisitEventCapture**: A class in `common/src/python/event_capture/event_capture.py` that writes `VisitEvent` objects as JSON files to an S3 transaction log bucket.
- **ErrorLogTemplate**: A class in `common/src/python/error_logging/error_logger.py` that generates QC status log filenames from `DataIdentification`.
- **FileVisitAnnotator**: A class in `common/src/python/error_logging/qc_status_log_creator.py` that annotates QC status log files with visit metadata.
- **Identification_Strategy**: A pluggable strategy that builds a `DataIdentification` from the input file and its Flywheel context. Different pipelines (forms, imaging) require different strategies.
- **GearExecutionEnvironment**: The abstract base class in `common/src/python/gear_execution/gear_execution.py` that all gear visitors extend, providing Flywheel client access and the standard `create`/`run` lifecycle.

## Requirements

### Requirement 1: Read Upstream Gear QC Outcome

**User Story:** As a pipeline operator, I want the Pipeline_Event_Logger to read the QC outcome written by an upstream gear, so that the result can be propagated to NACC's logging systems without modifying the upstream gear.

#### Acceptance Criteria

1. WHEN the Pipeline_Event_Logger is invoked with an input file and an `upstream_gear_name` configuration parameter, THE Pipeline_Event_Logger SHALL read the QC metadata from `file.info.qc.{upstream_gear_name}` using `FileQCModel`.
2. WHEN the `file.info.qc.{upstream_gear_name}` section exists and contains a valid `GearQCModel`, THE Pipeline_Event_Logger SHALL extract the QC status (PASS, FAIL, or IN REVIEW) and the error list from the validation model.
3. IF the `file.info.qc` section does not exist on the input file, THEN THE Pipeline_Event_Logger SHALL report an error and terminate with a failure status.
4. IF the `file.info.qc.{upstream_gear_name}` section does not exist within the QC metadata, THEN THE Pipeline_Event_Logger SHALL report an error and terminate with a failure status.

### Requirement 2: Build Data Identification

**User Story:** As a pipeline operator, I want the Pipeline_Event_Logger to construct a `DataIdentification` from the input file's context, so that QC log entries and events reference the correct visit/file.

#### Acceptance Criteria

1. THE Pipeline_Event_Logger SHALL read `DataIdentification` from `file.info.data_identification` on the input file, deserializing it via `DataIdentification.from_visit_metadata()`.
2. IF `file.info.data_identification` does not exist on the input file, THEN THE Pipeline_Event_Logger SHALL report an error and terminate with a failure status.
3. IF `file.info.data_identification` contains invalid or incomplete data, THEN THE Pipeline_Event_Logger SHALL report an error and terminate with a failure status.

> **Dependency**: Upstream gears must write a serialized `DataIdentification` to `file.info.data_identification`. For the imaging pipeline, this requires modifying the `image_identifier_lookup` gear (tracked separately).

### Requirement 3: Update Project-Level QC Status Log

**User Story:** As a pipeline operator, I want the Pipeline_Event_Logger to update the project-level QC status log for the processed visit/file, so that downstream systems can read a consolidated QC history.

#### Acceptance Criteria

1. WHEN a valid `DataIdentification` and QC outcome have been obtained, THE Pipeline_Event_Logger SHALL update the project-level QC status log with the visit identification, the upstream gear name, the extracted QC status, and the extracted error list.
2. THE Pipeline_Event_Logger SHALL ensure the QC status log file is annotated with visit metadata.
3. THE Pipeline_Event_Logger SHALL attribute the QC log entry to the upstream gear name, not to the Pipeline_Event_Logger gear name.
4. IF the QC status log update fails, THEN THE Pipeline_Event_Logger SHALL log a warning but continue processing (QC log update failure is non-critical).

### Requirement 4: Capture Visit Event to S3

**User Story:** As a pipeline operator, I want the Pipeline_Event_Logger to optionally capture a `VisitEvent` to the S3 transaction log, so that downstream analytics systems can track pipeline activity.

#### Acceptance Criteria

1. THE Pipeline_Event_Logger SHALL allow the operator to configure event actions per QC outcome, mapping outcome keys (`"pass"`, `"fail"`, `"in-review"`) to event action strings (e.g., `"pass-qc"`, `"not-pass-qc"`), along with the S3 destination for event capture.
2. WHEN event capture is configured and the QC outcome has a matching event action, THE Pipeline_Event_Logger SHALL create a `VisitEvent` with the matched action, the `DataIdentification`, the resolved timestamp, and the upstream gear name.
3. WHEN a `VisitEvent` is successfully created, THE Pipeline_Event_Logger SHALL write the event to the S3 transaction log.
4. WHEN the QC outcome does not have a matching event action in the configuration, THE Pipeline_Event_Logger SHALL skip event capture for that outcome.
5. WHEN event capture is not configured, THE Pipeline_Event_Logger SHALL skip event capture entirely.
6. IF event capture fails, THEN THE Pipeline_Event_Logger SHALL log a warning but continue processing (event capture failure is non-critical).

### Requirement 5: Resolve Event Timestamp

**User Story:** As a pipeline operator, I want the Pipeline_Event_Logger to use the most accurate timestamp available for events, so that the event log reflects when the upstream gear actually processed the file.

#### Acceptance Criteria

1. WHEN `file.info.validated-timestamp` exists on the input file, THE Pipeline_Event_Logger SHALL use the `validated-timestamp` value as the event timestamp.
2. WHEN `file.info.validated-timestamp` does not exist on the input file, THE Pipeline_Event_Logger SHALL fall back to `file.modified` as the event timestamp.

### Requirement 6: Gear Configuration and Inputs

**User Story:** As a pipeline operator, I want to configure the Pipeline_Event_Logger with the upstream gear name and event parameters, so that the gear can be reused across different pipeline stages.

#### Acceptance Criteria

1. THE Pipeline_Event_Logger SHALL accept a single Flywheel file as input.
2. THE Pipeline_Event_Logger SHALL require a configuration parameter that identifies the upstream gear whose QC results to read.
3. THE Pipeline_Event_Logger SHALL accept optional configuration parameters for event capture (action, S3 destination).
4. THE Pipeline_Event_Logger SHALL accept a configuration parameter for the API key path prefix used to authenticate with Flywheel.

### Requirement 7: Gear Structure and Execution Pattern

**User Story:** As a developer, I want the Pipeline_Event_Logger to follow the standard NACC gear architecture, so that the gear is consistent with the rest of the monorepo.

#### Acceptance Criteria

1. THE Pipeline_Event_Logger SHALL follow the standard gear directory structure: `gear/pipeline_event_logger/src/docker/` for Docker files and manifest, `gear/pipeline_event_logger/src/python/pipeline_event_logger_app/` for application code, and `gear/pipeline_event_logger/test/python/` for tests.
2. THE Pipeline_Event_Logger SHALL implement `GearExecutionEnvironment` with a `create()` class method that initializes dependencies from the gear context and a `run()` method that executes the workflow.
3. THE Pipeline_Event_Logger SHALL separate Flywheel context management in `run.py` from business logic in `main.py`, following the standard gear architecture.
4. THE Pipeline_Event_Logger SHALL use `GearEngine.create_with_parameter_store().run()` as the entry point in `run.py`.

### Requirement 8: Error Handling and Logging

**User Story:** As a pipeline operator, I want clear error reporting when the Pipeline_Event_Logger encounters problems, so that I can diagnose and resolve issues.

This gear distinguishes between critical failures (the gear cannot do its job) and non-critical failures (a downstream side effect failed but the gear's core work is done). This follows the pattern established in the `image_identifier_lookup` gear, where QC log updates and event captures are wrapped in try/except blocks that log warnings but do not fail the gear.

- **Critical failures** cause the gear to terminate with `GearExecutionError`: these are situations where the gear has no data to work with (missing input file, missing QC metadata, unresolvable data identification).
- **Non-critical failures** are logged as warnings and the gear continues: these are downstream side effects (QC status log update, S3 event capture) where the upstream gear's QC result is already safely stored in `file.info.qc` and can be retried independently.

#### Acceptance Criteria

1. IF the input file cannot be retrieved from Flywheel, THEN THE Pipeline_Event_Logger SHALL raise a `GearExecutionError` with a descriptive message.
2. IF the parent project cannot be retrieved for the input file, THEN THE Pipeline_Event_Logger SHALL raise a `GearExecutionError` with a descriptive message.
3. THE Pipeline_Event_Logger SHALL log informational messages at each major step: reading QC metadata, building data identification, updating QC status log, and capturing events.
4. THE Pipeline_Event_Logger SHALL treat QC status log update failures and event capture failures as non-critical, logging warnings but not failing the gear. The rationale is that the upstream gear's QC result is already persisted in `file.info.qc` and these operations can be retried.
5. THE Pipeline_Event_Logger SHALL treat QC metadata read failures and data identification failures as critical, terminating with a `GearExecutionError`. The rationale is that without QC data or visit identification, the gear has no work to perform.
