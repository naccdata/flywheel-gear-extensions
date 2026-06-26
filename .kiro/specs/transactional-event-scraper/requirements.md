# Requirements Document

## Introduction

The Transactional Event Scraper is a gear designed to backfill event data by scraping existing form data error logs to approximate the event capture that will be done by the identifier-lookup and form-scheduling gears. This tool will generate submission and pass-qc events with best estimates of event times using the shared event capture utilities already established in the NACC Data Platform.

## Glossary

- **Event_Scraper**: The transactional event scraper gear
- **Error_Log**: Form data error log files containing QC status and timestamps
- **Visit_Event**: Event objects representing form submission or QC pass activities
- **Event_Capture**: Shared utility for logging visit events to S3 transaction log
- **QC_Status_Log**: Project-level error log files with QC metadata and timestamps
- **Pipeline_Project**: Flywheel project containing form data and QC status logs

## Requirements

### Requirement 1: Error Log Discovery and Processing

**User Story:** As a data platform administrator, I want to discover and process existing error logs, so that I can extract historical event data for backfilling.

#### Acceptance Criteria

1. WHEN the Event_Scraper runs on a Pipeline_Project, THE Event_Scraper SHALL discover all QC status log files in the project
2. WHEN processing QC status log files, THE Event_Scraper SHALL parse the log contents to extract gear execution timestamps and status information
3. WHEN a QC status log contains multiple gear entries, THE Event_Scraper SHALL process each gear entry separately
4. WHEN encountering malformed or unreadable log files, THE Event_Scraper SHALL log the error and continue processing other files

### Requirement 2: Event Generation from Error Logs

**User Story:** As a data platform administrator, I want to generate visit events from error log data, so that I can create historical event records for form submissions and QC passes.

#### Acceptance Criteria

1. WHEN a QC status log shows a form submission entry, THE Event_Scraper SHALL create a submission event with the timestamp from the log entry
2. WHEN a QC status log shows a gear with PASS status, THE Event_Scraper SHALL create a pass-qc event with the timestamp from the log entry
3. WHEN extracting visit metadata from error logs, THE Event_Scraper SHALL use the same ErrorLogTemplate pattern used by existing gears
4. WHEN creating visit events, THE Event_Scraper SHALL populate all required VisitEvent fields using metadata from the error log and project context
5. WHEN visit metadata is incomplete or invalid, THE Event_Scraper SHALL skip event creation for that entry and log a warning

### Requirement 3: Event Capture Integration

**User Story:** As a data platform administrator, I want the scraper to use existing event capture utilities, so that generated events are stored consistently with future event logging.

#### Acceptance Criteria

1. THE Event_Scraper SHALL use the shared VisitEventCapture utility for logging events
2. THE Event_Scraper SHALL create VisitEvent objects that conform to the established event schema
3. WHEN capturing events, THE Event_Scraper SHALL use the same S3 bucket structure and naming conventions as other gears
4. THE Event_Scraper SHALL support configurable environment prefixes (prod/dev) for event storage

### Requirement 4: Timestamp Extraction

**User Story:** As a data platform administrator, I want accurate timestamp estimation for events, so that the historical event timeline reflects the actual processing sequence.

#### Acceptance Criteria

1. WHEN extracting submission events, THE Event_Scraper SHALL use the QC status log file creation timestamp as the submission time
2. WHEN extracting pass-qc events, THE Event_Scraper SHALL use the QC status log file modification timestamp as the QC completion time
3. WHEN a QC status log file shows PASS status, THE Event_Scraper SHALL use the file modification time as the QC completion time

### Requirement 5: Project and Visit Context

**User Story:** As a data platform administrator, I want events to include proper project and visit context, so that they can be correlated with other platform activities.

#### Acceptance Criteria

1. WHEN processing error logs, THE Event_Scraper SHALL extract pipeline ADCID from the project metadata
2. WHEN creating events, THE Event_Scraper SHALL derive study and datatype information from the project label using PipelineLabel parsing
3. WHEN extracting visit information, THE Event_Scraper SHALL parse PTID, visit date, and module from the error log filename using ErrorLogTemplate
4. THE Event_Scraper SHALL set the gear_name field to "transactional-event-scraper" for all generated events

### Requirement 6: Batch Processing and Error Handling

**User Story:** As a data platform administrator, I want robust batch processing, so that the scraper can handle large numbers of error logs without failing completely on individual errors.

#### Acceptance Criteria

1. WHEN processing multiple projects, THE Event_Scraper SHALL continue processing remaining projects if one project fails
2. WHEN processing multiple error logs within a project, THE Event_Scraper SHALL continue processing remaining logs if one log fails
3. WHEN encountering API errors or network issues, THE Event_Scraper SHALL log the error and continue with the next item
4. THE Event_Scraper SHALL provide summary statistics of processed files, generated events, and encountered errors

### Requirement 7: Configuration and Execution

**User Story:** As a data platform administrator, I want configurable execution parameters, so that I can control the processing scope and behavior.

#### Acceptance Criteria

1. THE Event_Scraper SHALL process all QC status log files in the project where the gear is executed
2. THE Event_Scraper SHALL accept date range filters to limit processing to files within specific time periods
3. THE Event_Scraper SHALL support dry-run mode that logs what events would be created without actually capturing them
4. THE Event_Scraper SHALL accept S3 bucket configuration for event storage destination