# Requirements Document

## Introduction

This specification defines the addition of submission event logging to the identifier lookup gear. When the identifier lookup gear processes CSV files in the "nacc" direction (PTID to NACCID), it should create submit events for each visit, similar to the submission_logger gear. This will allow the identifier lookup gear to eventually replace the submission_logger gear, consolidating functionality and reducing redundancy.

## Glossary

- **Identifier_Lookup_Gear**: Flywheel gear that processes CSV files to add NACCID identifiers
- **CSVLoggingVisitor**: CSV visitor class that creates visit events for each row
- **VisitEventLogger**: Service that logs visit events to S3
- **VisitEvent**: Data structure representing a visit event with action, center, project, and visit information
- **Submit Event**: A visit event with action="submit" indicating data submission
- **AggregateCSVVisitor**: CSV visitor that combines multiple visitors to process CSV files
- **NACCIDLookupVisitor**: CSV visitor that performs identifier lookup and CSV transformation
- **QCStatusLogCSVVisitor**: CSV visitor that creates QC status logs for visits
- **S3BucketInterface**: Interface for interacting with S3 buckets for event storage

## Requirements

### Requirement 1

**User Story:** As a data pipeline operator, I want the identifier lookup gear to create submit events when processing CSV files with QC logging, so that visit submissions are tracked in the event log system.

#### Acceptance Criteria

1. WHEN the Identifier_Lookup_Gear processes a CSV file in "nacc" direction with QC status log management, THE Identifier_Lookup_Gear SHALL create a submit event for each valid visit row
2. WHEN a CSV row contains all required visit fields, THE Identifier_Lookup_Gear SHALL extract visit information and log a submit event
3. WHEN a CSV row is missing required visit fields, THE Identifier_Lookup_Gear SHALL skip event logging for that row without failing the entire operation
4. WHEN the Identifier_Lookup_Gear processes a CSV file in "center" direction, THE Identifier_Lookup_Gear SHALL not create submit events
5. WHEN event logging fails for a visit, THE Identifier_Lookup_Gear SHALL continue processing subsequent visits without failing the entire operation

### Requirement 2

**User Story:** As a developer, I want to use the CSVLoggingVisitor to create submit events, so that the implementation follows established patterns and is maintainable.

#### Acceptance Criteria

1. WHEN creating submit events, THE Identifier_Lookup_Gear SHALL use CSVLoggingVisitor with action="submit"
2. WHEN configuring the event logging visitor, THE Identifier_Lookup_Gear SHALL provide center label, project label, and gear name
3. WHEN extracting visit information, THE Identifier_Lookup_Gear SHALL use the module configurations to identify required fields
4. WHEN determining the timestamp for events, THE Identifier_Lookup_Gear SHALL use the file creation timestamp
5. WHEN setting the datatype for events, THE Identifier_Lookup_Gear SHALL use "form" as the datatype
6. WHEN a CSV row contains a packet field, THE Identifier_Lookup_Gear SHALL include the packet value in the submit event

### Requirement 3

**User Story:** As a developer, I want to integrate event logging using the AggregateCSVVisitor pattern, so that the solution is consistent with the existing refactored architecture.

#### Acceptance Criteria

1. WHEN processing CSV files in "nacc" direction with QC logging enabled, THE Identifier_Lookup_Gear SHALL use AggregateCSVVisitor to coordinate identifier lookup, QC logging, and event logging
2. WHEN creating the aggregate visitor for QC-enabled processing, THE Identifier_Lookup_Gear SHALL include CSVLoggingVisitor as one of the constituent visitors
3. WHEN QC logging is not enabled, THE Identifier_Lookup_Gear SHALL not include CSVLoggingVisitor in the aggregate visitor
4. WHEN any visitor fails, THE Identifier_Lookup_Gear SHALL continue processing with other visitors
5. WHEN all visitors complete, THE Identifier_Lookup_Gear SHALL report overall success based on identifier lookup results

### Requirement 4

**User Story:** As a system administrator, I want event logging to be properly configured, so that events are stored in the correct environment.

#### Acceptance Criteria

1. WHEN creating the VisitEventLogger, THE Identifier_Lookup_Gear SHALL provide the S3 bucket interface and environment configuration
2. WHEN the environment is not specified, THE Identifier_Lookup_Gear SHALL default to "prod" environment
3. WHEN the event bucket name is not specified, THE Identifier_Lookup_Gear SHALL default to "nacc-event-logs"
4. WHEN the S3 bucket is not accessible, THE Identifier_Lookup_Gear SHALL fail with a clear error message during initialization
5. WHEN the VisitEventLogger is created successfully, THE Identifier_Lookup_Gear SHALL use it for all event logging operations

### Requirement 5

**User Story:** As a developer, I want comprehensive test coverage for event logging functionality, so that the changes are reliable and maintainable.

#### Acceptance Criteria

1. WHEN testing event logging, THE Identifier_Lookup_Gear SHALL verify submit events are created for valid visit rows
2. WHEN testing with missing visit fields, THE Identifier_Lookup_Gear SHALL verify event logging is skipped gracefully
3. WHEN testing visitor coordination, THE Identifier_Lookup_Gear SHALL verify all three visitors (identifier lookup, QC logging, event logging) work together correctly
4. WHEN testing error scenarios, THE Identifier_Lookup_Gear SHALL verify event logging failures do not prevent identifier lookup
5. WHEN testing "center" direction, THE Identifier_Lookup_Gear SHALL verify no submit events are created

### Requirement 6

**User Story:** As a data pipeline operator, I want the identifier lookup gear to maintain backward compatibility, so that existing workflows continue to function correctly.

#### Acceptance Criteria

1. WHEN processing files in "center" direction, THE Identifier_Lookup_Gear SHALL maintain existing behavior without event logging
2. WHEN identifier lookup fails, THE Identifier_Lookup_Gear SHALL maintain existing error reporting behavior
3. WHEN QC logging fails, THE Identifier_Lookup_Gear SHALL maintain existing resilience behavior
4. WHEN event logging is added, THE Identifier_Lookup_Gear SHALL maintain the same output file format and QC metadata structure
5. WHEN all processing completes, THE Identifier_Lookup_Gear SHALL report success based on identifier lookup results, not event logging results
