# Requirements Document

## Introduction

When a center resubmits a visit packet without changes, the submission pipeline creates orphaned "submit" events in the transaction log. The identifier-lookup gear logs a "submit" event unconditionally, but form-transformer silently drops duplicates without logging any event. This leaves no signal to distinguish a duplicate resubmission from a legitimate submission still in progress.

This feature adds a "duplicate-submit" event type that form-transformer logs when it detects an existing visit (an identical resubmission). This gives downstream reporting an explicit signal to pair with and dismiss the orphaned "submit" event.

## Glossary

- **Form_Transformer**: The Flywheel gear (`form-transformer`) that transforms CSV visit records into JSON, detects duplicate submissions, and uploads results. It is the authoritative source for duplicate detection.
- **VisitEventCapture**: The component (`event_capture.event_capture.VisitEventCapture`) responsible for writing `VisitEvent` objects as JSON files to an S3 transaction log bucket.
- **VisitEvent**: The Pydantic model (`event_capture.visit_events.VisitEvent`) representing a transactional event for a participant visit. Contains action, data_identification, timestamps, and gear metadata.
- **VisitEventType**: The type literal defining valid event actions. Currently `"submit" | "delete" | "not-pass-qc" | "pass-qc"`.
- **FormPreprocessor**: The component (`preprocess.preprocessor.FormPreprocessor`) that performs preprocessing checks on visit records, including duplicate detection via `is_existing_visit()`.
- **CSVTransformVisitor**: The visitor class in form-transformer's `main.py` that processes CSV rows, accumulates existing (duplicate) visits, and manages the transformation batch.
- **DataIdentification**: The model (`nacc_common.data_identification.DataIdentification`) that encapsulates participant, visit, and data-type-specific identification fields.
- **Transaction_Log**: The S3 bucket storing event JSON files with naming pattern `{env}/log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visit_date}.json`.
- **S3BucketInterface**: The abstraction (`s3.s3_bucket.S3BucketInterface`) used by VisitEventCapture to write files to S3.

## Requirements

### Requirement 1: Extend VisitEventType with duplicate-submit action

**User Story:** As a reporting system consumer, I want a distinct event type for duplicate submissions, so that I can deterministically distinguish orphaned submits from legitimately unfinalized visits.

#### Acceptance Criteria

1. THE VisitEventType literal SHALL include `"duplicate-submit"` as a valid action value alongside the existing `"submit"`, `"delete"`, `"not-pass-qc"`, and `"pass-qc"` values.
2. THE `visit_events` module SHALL export an `ACTION_DUPLICATE_SUBMIT` constant of type `VisitEventType` with the value `"duplicate-submit"`.
3. WHEN a VisitEvent is created with action `"duplicate-submit"`, THE VisitEvent model SHALL accept the same required fields as any other action (study, project_label, center_label, gear_name, data_identification, datatype, timestamp) and apply the existing `validate_datatype_consistency` rules to the datatype and data_identification pairing.
4. WHEN a VisitEvent with action `"duplicate-submit"` is serialized, THE VisitEvent model SHALL produce the same flattened dictionary structure as other event types, including the renamed fields (`pipeline_adcid`, `visit_date`, `visit_number`) and all pass-through fields from data_identification.

### Requirement 2: Form-transformer logs duplicate-submit events

**User Story:** As a reporting system consumer, I want form-transformer to log a "duplicate-submit" event when it detects a duplicate submission, so that the transaction log contains explicit signal for each dropped duplicate.

#### Acceptance Criteria

1. WHEN `FormPreprocessor.is_existing_visit()` returns True for a visit record, THE Form_Transformer SHALL capture a `"duplicate-submit"` VisitEvent for that record.
2. THE captured `"duplicate-submit"` event SHALL contain a `DataIdentification` constructed from the transformed record (the post-transformation row passed to `is_existing_visit()`) using the module's configured `date_field`, including ptid, visit_date, module, visitnum, packet, naccid, and adcid as available in that record.
3. THE captured `"duplicate-submit"` event SHALL use `"form"` as the datatype value.
4. THE captured `"duplicate-submit"` event SHALL use the gear name `"form-transformer"` as the `gear_name` field.
5. THE captured `"duplicate-submit"` event SHALL use the Flywheel input file entry's `created` timestamp (the same source used by identifier-lookup for submit events) as the `timestamp` field.
6. THE captured `"duplicate-submit"` event SHALL use the destination project's label as the `project_label` field and the center identifier (ADCID-based label) as the `center_label` field, consistent with the values used for submit events on the same project.
7. IF `DataIdentification` cannot be constructed from the transformed record (due to missing or invalid fields), THEN THE Form_Transformer SHALL skip event capture for that record and SHALL log a warning without interrupting processing of the duplicate visit.
8. WHEN a duplicate-submit event is captured, THE Form_Transformer SHALL continue its existing behavior of copying downstream metadata for the duplicate visit (the event capture does not replace existing duplicate-handling logic).

### Requirement 3: VisitEventCapture dependency injection into form-transformer

**User Story:** As a developer, I want the form-transformer gear to receive a properly configured VisitEventCapture instance, so that it can write events to S3 without duplicating infrastructure setup logic.

#### Acceptance Criteria

1. THE Form_Transformer gear's manifest.json SHALL declare `event_bucket` (type: string, default: empty string) and `event_environment` (type: string, default: empty string) configuration options for specifying the S3 transaction log destination.
2. WHEN `event_bucket` and `event_environment` are both provided as non-empty strings, THE Form_Transformer gear's `run.py` SHALL create a `VisitEventCapture` instance using `S3BucketInterface.create_from_environment(event_bucket)` with the `event_environment` value, and pass it to the `run()` function in `main.py`.
3. IF `S3BucketInterface.create_from_environment()` raises an `S3InterfaceError` or `ClientError` during `VisitEventCapture` initialization, THEN THE Form_Transformer gear SHALL raise a `GearExecutionError` with a message indicating the S3 bucket could not be accessed.
4. IF `event_bucket` or `event_environment` is empty or not provided, THEN THE Form_Transformer gear SHALL pass `None` as the event capture parameter, and CSV processing SHALL continue normally without logging events and without raising an error.
5. THE `run()` function in `main.py` SHALL accept an `Optional[VisitEventCapture]` parameter and pass it to the `CSVTransformVisitor` constructor, making it available at the point where duplicate detection occurs in `visit_row`.

### Requirement 4: Duplicate-submit event S3 file naming

**User Story:** As a reporting pipeline operator, I want duplicate-submit event files to follow the same naming convention as other events, so that the existing S3 retrieval infrastructure can discover them.

#### Acceptance Criteria

1. WHEN a `"duplicate-submit"` event is written to S3, THE VisitEventCapture SHALL produce a filename matching the pattern `{env}/log-duplicate-submit-{YYYYMMDD-HHMMSS}-{adcid}-{project}-{ptid}-{visit_date}.json` where `{YYYYMMDD-HHMMSS}` is the event timestamp formatted identically to other actions.
2. THE filename for a `"duplicate-submit"` event SHALL be generated by the existing `create_event_filename()` method, which produces the same result for any event action value (the action string is interpolated directly into the filename).
3. THE hyphenated action value `"duplicate-submit"` SHALL pass through the filename generation unsanitized (the existing sanitization only applies to the project label's `/` and `\` characters), ensuring the resulting filename is compatible with downstream S3 retrieval patterns.

### Requirement 5: Form-transformer manifest configuration

**User Story:** As a platform administrator, I want to configure form-transformer with event capture settings through the gear manifest, so that the feature can be enabled per deployment without code changes.

#### Acceptance Criteria

1. THE form-transformer `manifest.json` SHALL include an `event_bucket` configuration option of type `string` that is optional and has no default value.
2. THE form-transformer `manifest.json` SHALL include an `event_environment` configuration option of type `string` that is optional, constrained to the enum values `["prod", "dev"]`, and has no default value.
3. WHEN both `event_bucket` and `event_environment` are omitted from the gear configuration, THE Form_Transformer SHALL operate identically to its behavior prior to the event capture feature (no S3 event writes, no errors raised due to missing event configuration).
4. IF only one of `event_bucket` or `event_environment` is provided while the other is omitted, THEN THE Form_Transformer SHALL skip event capture and log a warning message indicating that both options are required for event capture to be active.

### Requirement 6: One duplicate-submit event per duplicate visit record

**User Story:** As a reporting system consumer, I want exactly one duplicate-submit event per duplicate row in the input file, so that event counts accurately reflect submission volume.

#### Acceptance Criteria

1. WHEN `FormPreprocessor.is_existing_visit()` returns True for a row during `visit_row()` processing, THE Form_Transformer SHALL capture exactly one `"duplicate-submit"` event for that row at the point of detection (before adding the row to the existing-visits collection).
2. WHEN a single input CSV file contains both duplicate and non-duplicate rows, THE Form_Transformer SHALL capture `"duplicate-submit"` events only for the rows where `is_existing_visit()` returns True and SHALL NOT capture events for rows that proceed to the current batch as non-duplicates.
3. WHEN `is_existing_visit()` returns True but the downstream metadata copy later fails (causing the visit to be re-added to the current batch for reprocessing), THE Form_Transformer SHALL NOT capture a second `"duplicate-submit"` event during batch reprocessing — the single event captured at initial detection is the only event for that row.

### Requirement 7: Event capture failure does not block processing

**User Story:** As a platform operator, I want form-transformer to continue processing even if event capture fails, so that a transient S3 issue does not block legitimate data processing.

#### Acceptance Criteria

1. IF the `VisitEventCapture.capture_event()` call raises an exception after exhausting its retry logic, THEN THE Form_Transformer SHALL log a warning that identifies the affected record (subject and visit date) and continue processing the remaining records without altering the gear's overall success or failure exit status.
2. IF event capture fails for a duplicate record, THEN THE Form_Transformer SHALL still perform its existing behavior (copying downstream metadata or re-adding to batch) for that record.
3. IF event capture fails for one or more records in a batch, THEN THE Form_Transformer SHALL complete processing of all remaining records in the batch and SHALL NOT re-raise the event capture exception.
