# Requirements Document

## Introduction

This specification defines the refactoring of event logging in the form scheduler gear to simplify and correct the event logging process. The current implementation logs both submit events and QC outcome events by scraping QC status logs at both project and acquisition levels, based on false assumptions. The refactor will simplify this to only log QC-pass events for JSON files at the acquisition level, since submit events are now handled by the identifier lookup gear.

## Glossary

- **Form_Scheduler_Gear**: Flywheel gear that schedules and processes form data through pipelines
- **EventAccumulator**: Class that accumulates and logs visit events from QC status files
- **VisitEventLogger**: Service that logs visit events to S3
- **QC_Status_Log**: JSON file containing QC metadata for processed visits
- **JSON_File**: Form data file at acquisition level containing visit information
- **CSV_File**: Batch submission file at project level containing multiple visits
- **QC_Pass_Event**: Visit event with action="pass-qc" indicating successful QC completion
- **Submit_Event**: Visit event with action="submit" indicating data submission (handled by identifier lookup)
- **Project_Level**: Files stored at the Flywheel project container level
- **Acquisition_Level**: Files stored at the Flywheel acquisition container level within sessions/subjects

## Requirements

### Requirement 1

**User Story:** As a data pipeline operator, I want the form scheduler to only log QC-pass events for JSON files, so that event logging is simplified and accurate.

#### Acceptance Criteria

1. WHEN the Form_Scheduler_Gear processes a pipeline completion, THE Form_Scheduler_Gear SHALL only create QC-pass events for visits that pass QC validation
2. WHEN checking QC validation status, THE Form_Scheduler_Gear SHALL read QC status from the QC status log file's custom info (info.qc) using FileQCModel.get_file_status()
3. WHEN a visit fails QC validation, THE Form_Scheduler_Gear SHALL not create any events (no QC-fail events)
4. WHEN the Form_Scheduler_Gear encounters QC status logs for CSV files at project level, THE Form_Scheduler_Gear SHALL ignore them and not create any events
5. WHEN the Form_Scheduler_Gear encounters QC status logs for JSON files at project level, THE Form_Scheduler_Gear SHALL process them for potential QC-pass events
6. WHEN the Form_Scheduler_Gear processes a visit that has already been logged as submitted by identifier lookup, THE Form_Scheduler_Gear SHALL not create duplicate submit events

### Requirement 2

**User Story:** As a developer, I want the event logging to only process JSON files at acquisition level, so that the implementation is focused and efficient.

#### Acceptance Criteria

1. WHEN scanning for QC status logs, THE Form_Scheduler_Gear SHALL only examine QC status log files at project level that correspond to JSON files in the finalization queue
2. WHEN filtering QC status log files, THE Form_Scheduler_Gear SHALL only process files that correspond to JSON form data files
3. WHEN extracting visit metadata, THE Form_Scheduler_Gear SHALL use the visit details from QC status file custom info if available
4. WHEN visit details are not available in custom info, THE Form_Scheduler_Gear SHALL extract visit information from the forms.json metadata of the JSON file itself
5. WHEN determining file relevance, THE Form_Scheduler_Gear SHALL match QC status logs to their corresponding JSON files by visit metadata

### Requirement 3

**User Story:** As a developer, I want to remove complex event accumulation logic, so that the codebase is simpler and more maintainable.

#### Acceptance Criteria

1. WHEN refactoring the EventAccumulator, THE Form_Scheduler_Gear SHALL remove logic for handling submit events
2. WHEN refactoring the EventAccumulator, THE Form_Scheduler_Gear SHALL remove logic for handling QC-fail events  
3. WHEN refactoring the EventAccumulator, THE Form_Scheduler_Gear SHALL remove complex visitor pattern implementations for error accumulation
4. WHEN refactoring the EventAccumulator, THE Form_Scheduler_Gear SHALL remove duplicate prevention logic since only QC-pass events are logged
5. WHEN refactoring the EventAccumulator, THE Form_Scheduler_Gear SHALL simplify the file filtering logic to only process acquisition-level files

### Requirement 4

**User Story:** As a developer, I want to leverage visit metadata added to QC status files by FileVisitAnnotator, so that visit metadata extraction is reliable and consistent.

#### Acceptance Criteria

1. WHEN processing QC status logs, THE Form_Scheduler_Gear SHALL first attempt to extract visit metadata from the custom info section using VisitKeys structure
2. WHEN visit metadata is available in custom info as VisitKeys, THE Form_Scheduler_Gear SHALL use it for event creation with all required fields for VisitEvent
3. WHEN visit metadata is not available in custom info, THE Form_Scheduler_Gear SHALL fall back to extracting visit information from the forms.json metadata of the corresponding JSON file
4. WHEN using visit metadata from custom info, THE Form_Scheduler_Gear SHALL validate that VisitKeys contains required fields (ptid, date, module) for VisitEvent creation
5. WHEN visit metadata is incomplete or invalid, THE Form_Scheduler_Gear SHALL skip event logging for that visit

### Requirement 5

**User Story:** As a system administrator, I want event logging to be resilient and not interfere with pipeline processing, so that form scheduling remains reliable.

#### Acceptance Criteria

1. WHEN event logging encounters errors, THE Form_Scheduler_Gear SHALL log warnings but continue pipeline processing
2. WHEN QC status log files are missing or corrupted, THE Form_Scheduler_Gear SHALL skip event logging for those visits without failing
3. WHEN S3 event logging fails, THE Form_Scheduler_Gear SHALL log the error but not retry or fail the pipeline
4. WHEN visit metadata extraction fails, THE Form_Scheduler_Gear SHALL log a warning and continue processing other visits
5. WHEN the event logger is not configured, THE Form_Scheduler_Gear SHALL skip event logging entirely without errors

### Requirement 6

**User Story:** As a developer, I want the refactored solution to maintain compatibility with existing event log consumers, so that downstream systems continue to work.

#### Acceptance Criteria

1. WHEN creating QC-pass events, THE Form_Scheduler_Gear SHALL maintain the same event structure and field names as before
2. WHEN logging events to S3, THE Form_Scheduler_Gear SHALL use the same bucket structure and file naming conventions
3. WHEN setting event timestamps, THE Form_Scheduler_Gear SHALL use the QC completion time from the status log file
4. WHEN including visit metadata in events, THE Form_Scheduler_Gear SHALL preserve all required fields (ptid, visit_date, visit_number, module, packet)
5. WHEN determining the gear name for events, THE Form_Scheduler_Gear SHALL use "form-scheduler" as the gear_name field

### Requirement 7

**User Story:** As a developer, I want to extend VisitKeys with a new data model that includes packet information and update FileVisitAnnotator to use it, so that all visit metadata needed for VisitEvent creation is available in QC status log annotations.

#### Acceptance Criteria

1. WHEN creating visit metadata for QC status log annotation, THE Form_Scheduler_Gear SHALL use a new data model that extends VisitKeys
2. WHEN the extended visit metadata model is defined, THE Form_Scheduler_Gear SHALL include an optional packet field for form packet information
3. WHEN FileVisitAnnotator.annotate_qc_log_file() is called, THE Form_Scheduler_Gear SHALL use the extended visit metadata model instead of base VisitKeys for annotation
4. WHEN FileVisitAnnotator creates visit metadata for annotation, THE Form_Scheduler_Gear SHALL include packet information from the source data in the extended model
5. WHEN extracting visit metadata from QC status custom info, THE Form_Scheduler_Gear SHALL use the extended model to access packet information for VisitEvent creation

### Requirement 8

**User Story:** As a developer, I want comprehensive test coverage for the simplified event logging, so that the refactored code is reliable.

#### Acceptance Criteria

1. WHEN testing QC-pass event creation, THE Form_Scheduler_Gear SHALL verify events are only created for visits that pass QC
2. WHEN testing file filtering, THE Form_Scheduler_Gear SHALL verify only acquisition-level JSON files are processed
3. WHEN testing visit metadata extraction, THE Form_Scheduler_Gear SHALL verify both custom info and JSON file fallback methods work correctly
4. WHEN testing error handling, THE Form_Scheduler_Gear SHALL verify event logging failures don't affect pipeline processing
5. WHEN testing integration, THE Form_Scheduler_Gear SHALL verify the simplified EventAccumulator works correctly with FormSchedulerQueue