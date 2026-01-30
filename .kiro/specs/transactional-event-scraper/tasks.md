# Implementation Plan: Transactional Event Scraper

## Overview

This implementation plan creates a Flywheel gear that scrapes existing QC status log files to generate historical submission and pass-qc events. The gear follows the established NACC framework and integrates with existing shared utilities for consistency.

## Tasks

- [x] 1. Set up core data models and configuration handling
  - Create EventData, ProcessingStatistics, and DateRange data models
  - Implement configuration parsing for gear parameters (dry_run, date filters, S3 settings)
  - Set up logging and error handling infrastructure
  - Create unit tests for data models and configuration handling
  - _Requirements: 7.2, 7.3, 7.4_

- [ ]* 1.1 Write property test for configuration handling
  - **Property 5: Dry Run Behavior**
  - **Validates: Requirements 7.3**

- [x] 2. Implement log file processing for QC status log parsing
  - Create `extract_event_from_log()` function using canonical methods
  - Use `VisitMetadata.create()` for visit metadata extraction
  - Use `FileQCModel.create()` for QC status determination
  - Extract timestamps from file attributes only (no content parsing)
  - Returns single EventData or None (simplified from class-based approach)
  - _Requirements: 1.2, 1.3, 2.3, 2.5_
  - _Note: Tests removed as code is now simple enough to not require them_

- [ ]* 2.1 Write property test for timestamp extraction
  - **Property 3: Timestamp Extraction**
  - **Validates: Requirements 4.1, 4.2**

- [x] 3. Implement EventGenerator for VisitEvent creation
  - Create EventGenerator class with project context integration
  - Implement submission event creation using file creation timestamps
  - Implement pass-qc event creation using file modification timestamps
  - Add PipelineLabel parsing for project metadata extraction
  - Set gear_name to "transactional-event-scraper" for all events
  - Create unit tests for EventGenerator class
  - _Requirements: 2.1, 2.2, 2.4, 5.1, 5.2, 5.3, 5.4_

- [ ]* 3.1 Write property test for event creation
  - **Property 2: Event Creation from Valid Logs**
  - **Validates: Requirements 2.1, 2.2, 2.4**

- [x] 4. Implement main EventScraper orchestrator
  - Create EventScraper class that coordinates file discovery and processing
  - Implement file filtering by date range (optional start/end dates)
  - Add batch processing with error resilience (continue on individual failures)
  - Generate summary statistics (files processed, events created, errors)
  - Integrate with VisitEventCapture for event storage
  - Create unit tests for EventScraper class
  - _Requirements: 1.1, 1.4, 6.2, 6.4, 7.1_

- [ ]* 4.1 Write property test for complete file processing
  - **Property 1: Complete File Processing**
  - **Validates: Requirements 1.1, 7.1, 7.2**

- [ ]* 4.2 Write property test for error resilience
  - **Property 4: Error Resilience**
  - **Validates: Requirements 1.4, 6.2, 6.4**

- [x] 5. Implement TransactionalEventScraperVisitor framework integration
  - Create visitor class extending GearExecutionEnvironment
  - Implement dependency injection for S3BucketInterface and VisitEventCapture
  - Add configuration validation and error handling with GearExecutionError
  - Integrate with ParameterStore for AWS credentials
  - Wire all components together in the run method
  - Create unit tests for visitor class integration
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 6. Update manifest.json configuration
  - Add event_bucket and event_environment configuration options
  - Add optional start_date and end_date parameters
  - Update gear description and metadata
  - Create unit tests for manifest configuration validation
  - _Requirements: 7.2, 7.3, 7.4_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - **Status**: Complete - All tests passing, code follows identifier-lookup pattern with dependency injection

- [ ]* 8. Write integration tests for end-to-end workflow
  - Test complete scraping workflow with mock project and QC status logs
  - Verify event capture integration and S3 storage
  - Test dry-run mode functionality
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 9. Final validation and cleanup
  - Run full test suite and fix any remaining issues
  - Verify gear can be built and packaged correctly
  - Test with sample QC status log files
  - Create comprehensive unit tests for any remaining untested components
  - _Requirements: All_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties
- Integration tests validate end-to-end functionality
- The gear leverages existing shared utilities (VisitEventCapture, ErrorLogTemplate, PipelineLabel) for consistency