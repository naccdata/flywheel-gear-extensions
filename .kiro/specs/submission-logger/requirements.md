# Requirements Document

## Introduction

The submission-logger gear captures "submit" events when new files are uploaded to ingest projects. It serves as the first step in the event logging pipeline, extracting visit information from uploaded data, logging submit events for each visit, and creating initial QC status logs at the project level to support downstream pipeline processing.

## Glossary

- **Submission Logger**: The Flywheel gear that processes file uploads and creates submit events
- **Visit Event**: A structured data object representing an action (submit, pass-qc, not-pass-qc, delete) on visit data
- **QC Status Log**: A project-level file that tracks quality control status for a visit throughout pipeline processing
- **PTID**: Participant identifier used to uniquely identify study participants
- **Visit Date**: The date of a participant's visit, serving as the primary key for visit identification
- **Module**: Form module identifier (UDS, FTLD, LBD, etc.) specific to form data types
- **Ingest project**: The Flywheel project to which data is uploaded and where pipeline gears operate
- **Pipeline ADCID**: Alzheimer's Disease Center identifier used for event routing
- **S3 Event Storage**: AWS S3 bucket system for storing structured event logs

## Constraints

### Technical Architecture Constraints

1. **Dynamic Dispatch Pattern**: The implementation SHALL use dynamic dispatch (visitor pattern or similar) to support different input file types, enabling extensible file processing without modifying core logic
2. **Event Logging Infrastructure**: The implementation SHALL use the existing `common.event_logging` module classes, specifically `VisitEventLogger` for S3 event storage and established filename conventions
3. **QC Status Log Naming**: The implementation SHALL use the `ErrorLogTemplate` model class from `common.configs.ingest_configs` to generate QC status log file names following established patterns
4. **Gear Structure Conventions**: The implementation SHALL follow the established gear directory structure and coding patterns, using `gear/identifier_lookup` as the primary reference for CSV file processing patterns

### Integration Constraints

5. **Flywheel Gear Architecture**: The implementation SHALL integrate with the Flywheel gear execution framework using `GearExecutionEnvironment` and related classes
6. **Existing Infrastructure**: The implementation SHALL leverage existing common libraries for centers, identifiers, data processing, and Flywheel adapters without duplicating functionality
7. **Error Handling Patterns**: The implementation SHALL follow established error handling patterns from other gears, using `ListErrorWriter` and `FileError` classes for consistent error reporting

## Requirements

### Requirement 1

**User Story:** As a data pipeline operator, I want submit events to be automatically logged when files are uploaded, so that I can track all data submissions in the transaction log.

#### Acceptance Criteria

1. WHEN a file is uploaded to an ingest project THEN the Submission Logger SHALL process the file and extract visit information
2. WHEN visit information is successfully extracted THEN the Submission Logger SHALL create a submit event for each visit found in the file
3. WHEN a submit event is created THEN the Submission Logger SHALL log the event to S3 using the established event logging infrastructure
4. WHEN logging submit events THEN the Submission Logger SHALL use the file upload timestamp as the event timestamp
5. WHEN processing fails for any reason THEN the Submission Logger SHALL log detailed error information without failing the gear execution

### Requirement 2

**User Story:** As a data analyst, I want visit information to be extracted from uploaded files, so that I can track individual visits through the processing pipeline.

#### Acceptance Criteria

1. WHEN processing a CSV file THEN the Submission Logger SHALL parse the file content to identify individual visits
2. WHEN extracting visit metadata THEN the Submission Logger SHALL capture PTID, visit date, visit number, module, packet, and study information
3. WHEN visit date is present THEN the Submission Logger SHALL use it as the primary key for visit identification
4. WHEN visit number or module information is missing THEN the Submission Logger SHALL continue processing with available information
5. WHEN multiple visits are found in a single file THEN the Submission Logger SHALL process each visit independently

### Requirement 3

**User Story:** As a pipeline developer, I want QC status logs to be created for each visit, so that downstream gears can track quality control status throughout processing.

#### Acceptance Criteria

1. WHEN a visit is identified THEN the Submission Logger SHALL create a QC status log file at the project level
2. WHEN creating QC status logs THEN the Submission Logger SHALL use the naming pattern `{ptid}_{visitdate}_{module}_qc-status.log`
3. WHEN initializing QC status logs THEN the Submission Logger SHALL create an empty QC metadata structure ready for pipeline gears
4. WHEN visit information is available THEN the Submission Logger SHALL store visit metadata in the QC status log file
5. WHEN QC log creation fails THEN the Submission Logger SHALL log the error and continue processing remaining visits

### Requirement 4

**User Story:** As a system integrator, I want QC status log files to be annotated with visit metadata, so that downstream pipeline gears can access visit details for processing.

#### Acceptance Criteria

1. WHEN creating QC status log files THEN the Submission Logger SHALL add visit details to the QC log file metadata
2. WHEN storing visit metadata THEN the Submission Logger SHALL use the `file.info.visit` structure on QC status log files
3. WHEN visit information is extracted THEN the Submission Logger SHALL include PTID, visit date, visit number, module, packet, study, and center information in QC log metadata
4. WHEN QC log metadata enhancement fails THEN the Submission Logger SHALL log the error and continue with processing
5. WHEN processing uploaded CSV files THEN the Submission Logger SHALL NOT modify the uploaded file metadata or content in any way

### Requirement 5

**User Story:** As a data platform administrator, I want the submission logger to integrate with existing event logging infrastructure, so that submit events follow established patterns and storage conventions.

#### Acceptance Criteria

1. WHEN creating visit events THEN the Submission Logger SHALL use the established VisitEvent data model
2. WHEN logging events to S3 THEN the Submission Logger SHALL follow the established filename convention `log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json`
3. WHEN determining event metadata THEN the Submission Logger SHALL extract project and center information from Flywheel context
4. WHEN processing form data THEN the Submission Logger SHALL set datatype to "form" and include module information
5. WHEN handling non-form data types THEN the Submission Logger SHALL set appropriate datatype and omit form-specific fields

### Requirement 6

**User Story:** As a system operator, I want comprehensive error handling and logging, so that I can troubleshoot issues and ensure reliable operation.

#### Acceptance Criteria

1. WHEN file access errors occur THEN the Submission Logger SHALL log detailed warnings and continue processing
2. WHEN CSV parsing fails THEN the Submission Logger SHALL handle malformed data gracefully and report specific errors
3. WHEN event logging fails THEN the Submission Logger SHALL log the failure but not fail the gear execution
4. WHEN visit metadata is incomplete THEN the Submission Logger SHALL continue processing with available information
5. WHEN any processing step fails THEN the Submission Logger SHALL provide detailed error messages for troubleshooting

### Requirement 7

**User Story:** As a performance monitor, I want the submission logger to provide operational metrics, so that I can track processing efficiency and identify bottlenecks.

#### Acceptance Criteria

1. WHEN processing files THEN the Submission Logger SHALL log the number of files processed
2. WHEN extracting visits THEN the Submission Logger SHALL report the total number of visits identified
3. WHEN creating events THEN the Submission Logger SHALL confirm the number of submit events successfully logged
4. WHEN errors occur THEN the Submission Logger SHALL track error counts and types
5. WHEN processing completes THEN the Submission Logger SHALL provide summary statistics for monitoring


