# Changelog

All notable changes to this gear are documented in this file.

## 1.1.0

* Push unmatched submit events in Phase 3 instead of only warning — mirrors live pipeline where submit events are independent of JSON file availability
* Remove date filter from Phase 2 JSON file processing — date range now only controls which submissions are scraped, maximizing QC event matching
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)
* Fixed timezone-aware datetime comparison in date range filtering (Flywheel SDK returns UTC-aware timestamps)
* Fixed `from_forms_json` to extract only relevant keys from form data payload (was passing hundreds of form fields as kwargs)
* Added legacy filename fallback when looking up QC status logs (tries with visitnum first, then without)
* Added NP module date field support (`npformdate` instead of `visitdate`)
* Date field resolution falls back to `visitdate` when module-specific field is not present
* Improved error logging: `_extract_from_filename` now raises instead of swallowing errors, caller logs the reason
* Added warning-level logging in Phase 2 when metadata extraction or QC log lookup fails
* Reload JSON files before accessing `.info` metadata (files.find() returns incomplete objects)
* Removed `debug` config option from manifest

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
