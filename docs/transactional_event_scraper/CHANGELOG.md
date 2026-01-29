# Changelog

All notable changes to this gear are documented in this file.

## 0.0.2

* Fixed file discovery to properly retrieve FileEntry objects instead of file metadata dictionaries
* Resolved Pydantic validation errors that prevented event extraction
* Fixed metadata extraction failures that caused all files to be skipped

## 0.0.1

* Initial version
* Scrapes QC status log files to generate historical submission and pass-qc events
* Supports dry-run mode for testing without capturing events
* Supports date filtering to process files within a specific time range
* Captures events to S3 bucket with configurable environment prefixes
