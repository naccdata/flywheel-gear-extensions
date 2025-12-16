# Submission Logger Changelog

All notable changes to the submission logger gear will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial implementation of submission logger gear
- CSV file processing with form data validation
- Visit event logging to S3
- QC status log creation
- Processing metrics tracking
- Comprehensive error handling with custom exceptions
- Property-based testing with Hypothesis

### Changed
- Separated gear framework dependencies from business logic
- Moved ProcessingMetrics to shared common/metrics module
- Improved error handling with specific exception types
- Updated test suite to use new exception-based error handling

### Technical
- Dependency separation: main.py contains pure business logic
- run.py handles gear framework integration
- Custom exceptions: ConfigurationError, FileProcessingError
- Protocol-based abstraction for InputFileWrapper
- Type-safe implementation with mypy validation