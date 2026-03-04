# Implementation Plan: Image Identifier Lookup Gear

## Overview

This implementation plan converts the image identifier lookup design into actionable coding tasks. The gear performs NACCID lookups for DICOM images (one file = one lookup), using the refactored DataIdentification architecture with ImageIdentification. The implementation modifies existing template code in `gear/image_identifier_lookup` and maximizes code reuse from the `common/` package.

Key architectural principles:
- Standard gear pattern: run.py handles setup, main.py orchestrates workflow, processor.py contains business logic
- Early data extraction with fail-fast validation in run.py
- Idempotency checks to handle re-runs gracefully in main.py
- Separation of concerns: visitor handles Flywheel setup, main.py orchestrates, processor handles business logic
- Required event capture (gear fails if not configured)
- Comprehensive DICOM metadata extraction and storage

## Tasks

- [x] 1. Set up DICOM utilities and data extraction
  - [x] 1.1 Create DICOM parsing utilities
    - Create `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/dicom_utils.py`
    - Implement `read_dicom_tag(file_path, tag)` function using pydicom
    - Implement `InvalidDicomError` exception class
    - Handle DICOM parsing errors gracefully
    - _Requirements: 1.5, 1.8, 6.2, 6.9, 6.10, 6.11_

  - [x] 1.2 Write unit tests for DICOM parsing
    - Test reading valid DICOM tags (PatientID, StudyDate, Modality)
    - Test handling of missing optional tags (return None)
    - Test error handling for invalid DICOM files
    - Test extraction of all identifier and descriptive fields
    - _Requirements: 1.5, 6.9, 6.10, 6.11_

  - [x] 1.3 Create early data extraction utilities
    - Create `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/extraction.py`
    - Implement `extract_pipeline_adcid(project)` using ProjectAdaptor.get_pipeline_adcid()
    - Implement `extract_ptid(subject, file_path)` with subject.label priority, DICOM PatientID fallback
    - Implement `extract_existing_naccid(subject, naccid_field_name)` from subject.info
    - Implement `extract_visit_metadata(file_path, ptid, adcid, naccid, default_modality)` returning DataIdentification
    - Implement `extract_dicom_metadata(file_path)` for comprehensive metadata extraction
    - Implement `format_dicom_date(dicom_date)` to convert YYYYMMDD to YYYY-MM-DD
    - All functions should fail fast with clear error messages when required data is missing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 4.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.9, 6.10, 6.11_

  - [x] 1.4 Write unit tests for data extraction
    - Test extract_pipeline_adcid with valid and missing ADCID
    - Test extract_ptid with subject.label (primary path)
    - Test extract_ptid with DICOM PatientID fallback
    - Test extract_ptid failure when both sources empty
    - Test extract_existing_naccid with present and absent NACCID
    - Test extract_visit_metadata with valid DICOM data
    - Test extract_visit_metadata failure when StudyDate missing
    - Test extract_visit_metadata with missing modality (uses default)
    - Test extract_dicom_metadata with all fields present
    - Test extract_dicom_metadata with missing optional fields
    - Test format_dicom_date with valid and invalid dates
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 2.1, 2.2, 2.3, 6.1, 6.2, 6.3, 6.7, 6.9, 6.10, 6.11_

- [ ] 2. Implement core identifier lookup processor
  - [x] 2.1 Create processor with business logic
    - Create `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/processor.py`
    - Implement `ImageIdentifierLookupProcessor` class
    - Constructor accepts: identifiers_repository, subject, naccid_field_name
    - Implement `lookup_and_update(ptid, adcid, existing_naccid)` method
    - Implement `_lookup_naccid(ptid, adcid)` using IdentifiersLambdaRepository.get_naccid()
    - Implement `_update_subject_metadata(naccid, dicom_metadata)` to store NACCID and DICOM metadata in subject.info
    - Handle NACCID conflicts (existing differs from lookup result)
    - Processor receives pre-extracted data as parameters (no Flywheel object access)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 2.2 Write unit tests for processor
    - Test successful NACCID lookup and metadata update
    - Test lookup failure (no matching record)
    - Test lookup failure (repository unavailable)
    - Test NACCID conflict detection (existing differs from lookup)
    - Test metadata update with NACCID and DICOM metadata
    - Test metadata update failure handling
    - Use mocks for IdentifiersLambdaRepository and SubjectAdaptor
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.3, 4.4, 4.5, 4.6, 4.7_

- [ ] 3. Implement gear visitor and orchestration
  - [x] 3.1 Create visitor class with initialization
    - Create `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/run.py`
    - Implement `ImageIdentifierLookupVisitor` class extending GearExecutionEnvironment
    - Constructor accepts: client, file_input, identifiers_repository, event_capture, gear_name, naccid_field_name, default_modality
    - Implement `create(context, parameter_store)` factory method
    - Extract configuration: database_mode, naccid_field_name, default_modality, event_environment, event_bucket, admin_group
    - Initialize ClientWrapper (GearBotClient), InputFileWrapper, IdentifiersLambdaRepository
    - Initialize VisitEventCapture (required - fail if event_environment or event_bucket missing)
    - Verify S3 bucket accessibility during initialization
    - _Requirements: 7.1, 7.2, 7.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 3.2 Implement early data extraction in visitor run() method
    - Implement `run(context)` method in ImageIdentifierLookupVisitor
    - Retrieve input file, parent subject, and parent project
    - Extract all required data early (fail fast):
      - Pipeline ADCID from project metadata
      - PTID from subject.label or DICOM PatientID
      - Existing NACCID from subject.info (if present)
      - Visit metadata from DICOM (StudyDate, modality)
      - Comprehensive DICOM metadata for storage
    - Fail immediately if any required data is missing
    - Call main.run() with all extracted data
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.9, 6.10, 6.11_

  - [x] 3.3 Implement main orchestration function
    - Create `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/main.py`
    - Implement `run()` function that orchestrates the workflow
    - Accept all pre-extracted data as parameters (no Flywheel object access)
    - Check idempotency: if NACCID already exists, skip lookup
    - If no NACCID: create ImageIdentifierLookupProcessor and perform lookup
    - Update subject metadata with NACCID and DICOM metadata via processor
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 3.4 Implement QC logging and event capture in main.py
    - Create DataIdentification with ImageIdentification using extracted metadata
    - Update QC status log using QCStatusLogManager (PASS or FAIL)
    - Add visit metadata to log file on initial creation
    - Capture submission event using VisitEventCapture with action="submit", datatype="dicom"
    - Handle QC logging failures gracefully (log error, don't fail gear)
    - Handle event capture failures gracefully (log error, don't fail gear)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

  - [x] 3.5 Implement file QC metadata and tagging in main.py
    - Add QC metadata to input file with validation state (PASS or FAIL)
    - Add error information to file's QC metadata using FileErrorList format
    - Add gear tag to input file (gear-PASS or gear-FAIL)
    - Collect and report all errors in QC metadata
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 3.6 Write unit tests for visitor and main orchestration
    - Test successful end-to-end flow (extraction → lookup → update → QC → event)
    - Test idempotency (skip when NACCID already correct)
    - Test NACCID conflict detection
    - Test fail-fast on missing ADCID
    - Test fail-fast on missing PTID
    - Test fail-fast on missing StudyDate
    - Test QC logging on success and failure
    - Test event capture on success and failure
    - Test file QC metadata and tagging
    - Use mocks for all dependencies
    - _Requirements: All requirements_

- [x] 4. Checkpoint - Ensure core functionality works
  - Run unit tests for all components
  - Verify DICOM parsing works with sample files
  - Verify early extraction and fail-fast behavior
  - Verify idempotency logic
  - Ask the user if questions arise

- [ ] 5. Create main entry point and error handling
  - [x] 5.1 Update main entry point
    - The main.py already contains the orchestration logic (run() function)
    - Entry point is in run.py's main() function which calls GearEngine
    - No additional changes needed for basic entry point
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 5.2 Implement error handling utilities
    - Create `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/errors.py`
    - Implement `ErrorHandler` class with centralized error handling
    - Implement `create_ptid_extraction_error(error)` method
    - Implement `create_lookup_error(ptid, adcid, error)` method
    - Implement `create_metadata_conflict_error(ptid, existing, new)` method
    - Implement `create_dicom_parsing_error(error)` method
    - All error methods return FileError objects with appropriate context
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 5.3 Write integration tests
    - Test end-to-end success flow with real DICOM file
    - Test end-to-end failure flow (lookup fails)
    - Test idempotent re-run (NACCID already exists)
    - Test NACCID conflict scenario
    - Test fail-fast scenarios (missing ADCID, PTID, StudyDate)
    - Test QC log creation and event capture
    - Use test fixtures and mocked AWS services
    - _Requirements: All requirements_

- [ ] 6. Update gear configuration and dependencies
  - [x] 6.1 Update manifest.json
    - Update `gear/image_identifier_lookup/src/docker/manifest.json`
    - Add config parameters: database_mode, naccid_field_name, default_modality, event_environment, event_bucket, admin_group, apikey_path_prefix
    - Define input_file input with type constraint: dicom
    - Define api-key input
    - Set gear metadata: name, label, version, category, suite
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 6.2 Verify BUILD file configuration
    - Verify `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/BUILD` exists
    - Confirm Pants dependency inference is working (no explicit dependencies needed)
    - The existing BUILD file with `python_sources()` and `pex_binary()` is sufficient
    - Pants will automatically infer dependencies from import statements
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.10_

  - [x] 6.3 Update Dockerfile
    - Update `gear/image_identifier_lookup/src/docker/Dockerfile`
    - Ensure pydicom is installed
    - Set correct entrypoint to main.py
    - Verify Python 3.12 base image
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.10_

- [ ] 7. Final testing and validation
  - [ ]* 7.1 Run all unit tests
    - Execute: `./bin/exec-in-devcontainer.sh pants test gear/image_identifier_lookup/test/python::`
    - Verify all tests pass
    - _Requirements: All requirements_

  - [ ]* 7.2 Run code quality checks
    - Execute: `./bin/exec-in-devcontainer.sh pants fix gear/image_identifier_lookup::`
    - Execute: `./bin/exec-in-devcontainer.sh pants lint gear/image_identifier_lookup::`
    - Execute: `./bin/exec-in-devcontainer.sh pants check gear/image_identifier_lookup::`
    - Fix any issues found
    - _Requirements: 12.7_

  - [ ]* 7.3 Build Docker image
    - Execute: `./bin/exec-in-devcontainer.sh pants package gear/image_identifier_lookup/src/docker::`
    - Verify image builds successfully
    - _Requirements: 12.10_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Verify all unit tests pass
  - Verify all integration tests pass
  - Verify code quality checks pass
  - Verify Docker image builds
  - Ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The design uses Python (not pseudocode), so implementation is in Python
- Existing template code in `gear/image_identifier_lookup` will be modified
- Maximum code reuse from `common/` package and existing gears
- DataIdentification with ImageIdentification architecture is already implemented and ready to use
- Event capture is REQUIRED - gear fails if not configured
- Early extraction with fail-fast validation prevents wasted processing
- Idempotency checks enable safe re-runs
- QC logging and event capture failures are non-critical (logged but don't fail gear)
