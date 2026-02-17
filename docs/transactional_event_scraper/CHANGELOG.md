# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.0.0

* Major refactoring to support packet information enrichment
* Implemented three-phase processing workflow:
  - Phase 1: Process QC status logs to create submit events
  - Phase 2: Process form JSON files to create QC events and match with submit events
  - Phase 3: Report unmatched events for investigation
* Submit events are now enriched with packet information from form JSON files
* Added event matching logic to correlate submit events with QC events based on ptid, date, and module
* Improved logging to track unmatched events and potential data loss scenarios
* Removed ProcessingStatistics model in favor of direct logging
* Added support for discovering and processing form JSON files from acquisitions
* Enhanced error handling and resilience for individual file processing failures
* Updated tests to verify new three-phase workflow
* All type checks and tests passing

## 0.0.4

* Removed unused `log_file` field from EventData model
* Simplified data model to only include fields actually used by event generation
* Added fallback to filename parsing for extracting visit metadata from older QC status logs
* Now supports both newer files (with info.visit metadata) and older files (without metadata)
* Implements two-tier metadata extraction: custom info first, then filename parsing
* Uses shared QC filename pattern from `nacc_common.qc_report` to avoid duplication
* Fixed file discovery to reload FileEntry objects to get full metadata
* Resolved Pydantic validation errors caused by incomplete file objects

## 0.0.3

* Fixed file discovery to reload FileEntry objects to get full metadata
* Resolved Pydantic validation errors caused by incomplete file objects
* Fixed metadata extraction failures that caused all files to be skipped

## 0.0.2

* Incorrect fix attempt (do not use this version)

## 0.0.1

* Initial version
* Scrapes QC status log files to generate historical submission and pass-qc events
* Supports dry-run mode for testing without capturing events
* Supports date filtering to process files within a specific time range
* Captures events to S3 bucket with configurable environment prefixes
