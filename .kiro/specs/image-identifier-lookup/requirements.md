# Requirements Document

## Introduction

This specification defines the Image Identifier Lookup gear, which performs NACCID lookups for DICOM images uploaded to the NACC Data Platform. The gear runs on a single image file as input, performing one lookup per file (the file is the unit of data). The gear uses the PatientID DICOM tag (stored in subject.label) to look up the corresponding NACCID and store it in subject metadata. The gear creates QC status logs for tracking and uses transactional event capture to log submission events.

This implementation will modify the existing template code in `gear/image_identifier_lookup` and should maximize reuse of existing code from the `common/` package and other gears, particularly the identifier lookup gear and form processing gears that implement QC status logging and event capture.

### Context

This gear follows similar patterns to the `identifier_lookup` gear, which performs identifier lookups for CSV files. The key architectural difference is the unit of processing: this gear processes one image file per execution (one file = one lookup), while the CSV-based gear processes multiple participant records in a single file (one row = one lookup).

## Glossary

- **Image_Identifier_Lookup_Gear**: Flywheel gear that performs NACCID lookups for DICOM images
- **PatientID**: DICOM tag (0010,0020) containing the patient identifier, typically stored in subject.label on upload
- **PTID**: Participant ID used for identifier lookup, obtained from subject.label or DICOM PatientID tag
- **NACCID**: NACC identifier for participants
- **ADCID**: ADRC identifier
- **Pipeline_ADCID**: The ADCID associated with a pipeline project, stored in project metadata
- **Subject**: Flywheel subject container representing a participant
- **QC_Status_Log**: Project-level error log file tracking QC status for the lookup operation
- **Visit_Event**: Event object representing the image submission activity
- **Event_Capture**: Shared utility for logging events to S3 transaction log
- **Identifiers_Repository**: Service for looking up identifier mappings (PTID/ADCID to NACCID)
- **AcquisitionDate**: DICOM tag (0008,0022) containing the date the image was acquired
- **Modality**: DICOM tag (0008,0060) describing the imaging modality (e.g., MR, CT, PET)
- **ImageVisitMetadata**: Base metadata class for image visit information, extending from a generalized visit metadata structure
- **pydicom**: Python package for reading and parsing DICOM files

## Requirements

### Requirement 1: PTID Retrieval from Subject and DICOM File

**User Story:** As a data platform administrator, I want the gear to retrieve the PTID from subject.label or the DICOM file header, so that the identifier lookup can be performed even when subject.label is not set.

#### Acceptance Criteria

1. WHEN the Image_Identifier_Lookup_Gear runs, THE Image_Identifier_Lookup_Gear SHALL process exactly one input image file
2. WHEN retrieving the PTID, THE Image_Identifier_Lookup_Gear SHALL first attempt to retrieve the parent subject for the input image file
3. WHEN the subject exists and subject.label is set (not empty), THE Image_Identifier_Lookup_Gear SHALL use subject.label as the PTID
4. WHEN the subject.label is empty or missing, THE Image_Identifier_Lookup_Gear SHALL read the PatientID tag (0010,0020) from the DICOM file header as a fallback
5. WHEN reading the DICOM file header, THE Image_Identifier_Lookup_Gear SHALL use pydicom to parse the DICOM file
6. WHEN both subject.label and the DICOM PatientID tag are empty or missing, THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message
7. WHEN the gear performs identifier lookup, THE Image_Identifier_Lookup_Gear SHALL perform exactly one lookup for the file (the file is the unit of data)
8. WHEN the input file is not a valid DICOM file and subject.label is not set, THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message

### Requirement 2: Pipeline ADCID Retrieval

**User Story:** As a data platform administrator, I want the gear to retrieve the pipeline ADCID from the project, so that the identifier lookup can be performed with the correct center context.

#### Acceptance Criteria

1. WHEN the Image_Identifier_Lookup_Gear runs, THE Image_Identifier_Lookup_Gear SHALL retrieve the parent project for the input image file
2. WHEN retrieving project information, THE Image_Identifier_Lookup_Gear SHALL extract the pipeline ADCID from project metadata using ProjectAdaptor.get_pipeline_adcid()
3. WHEN the pipeline ADCID is missing from project metadata, THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message
4. WHEN the pipeline ADCID is invalid or malformed, THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message

### Requirement 3: NACCID Lookup

**User Story:** As a data platform administrator, I want the gear to look up the NACCID using the PTID and ADCID, so that the image can be associated with the correct participant identifier.

#### Acceptance Criteria

1. WHEN performing identifier lookup, THE Image_Identifier_Lookup_Gear SHALL use the IdentifiersLambdaRepository with the configured database mode
2. WHEN looking up the NACCID, THE Image_Identifier_Lookup_Gear SHALL query using both PTID (from subject.label or DICOM PatientID tag) and ADCID (from project metadata)
3. WHEN the identifier lookup succeeds, THE Image_Identifier_Lookup_Gear SHALL retrieve the NACCID value
4. WHEN the identifier lookup fails (no matching record), THE Image_Identifier_Lookup_Gear SHALL record an error and fail the QC check
5. WHEN the identifier lookup service is unavailable, THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message

### Requirement 4: Subject Metadata Update

**User Story:** As a data platform administrator, I want the NACCID to be stored in subject metadata, so that it can be used by downstream processes and is easily accessible.

#### Acceptance Criteria

1. WHEN the NACCID lookup succeeds, THE Image_Identifier_Lookup_Gear SHALL store the NACCID in subject.info using a configurable field name
2. WHEN the subject metadata field name is not configured, THE Image_Identifier_Lookup_Gear SHALL use "naccid" as the default field name
3. WHEN the NACCID field already exists in subject.info with the same value, THE Image_Identifier_Lookup_Gear SHALL skip the update and mark the operation as successful
4. WHEN the NACCID field already exists in subject.info with a different value, THE Image_Identifier_Lookup_Gear SHALL record an error and fail the QC check
5. WHEN updating subject metadata fails due to API errors, THE Image_Identifier_Lookup_Gear SHALL record an error and fail the QC check

### Requirement 5: QC Status Log Creation

**User Story:** As a data platform administrator, I want a QC status log to be created for the lookup operation, so that I can track the success or failure of the identifier lookup.

#### Acceptance Criteria

1. WHEN processing the input image file, THE Image_Identifier_Lookup_Gear SHALL create a QC status log file at the project level
2. WHEN creating the QC status log filename, THE Image_Identifier_Lookup_Gear SHALL use a naming pattern with PTID, AcquisitionDate, and modality (e.g., "{PTID}_{AcquisitionDate}_{modality}_qc.json")
3. WHEN the identifier lookup succeeds, THE Image_Identifier_Lookup_Gear SHALL update the QC status log with PASS status
4. WHEN the identifier lookup fails, THE Image_Identifier_Lookup_Gear SHALL update the QC status log with FAIL status and error details
5. WHEN QC status log creation fails, THE Image_Identifier_Lookup_Gear SHALL log the error but continue processing
6. WHEN updating the QC status log, THE Image_Identifier_Lookup_Gear SHALL use the QCStatusLogManager with appropriate ImageVisitMetadata
7. WHEN creating the initial QC status log, THE Image_Identifier_Lookup_Gear SHALL add visit metadata to the log file using FileVisitAnnotator with ImageVisitMetadata structure

### Requirement 6: Visit Metadata Extraction

**User Story:** As a data platform administrator, I want visit information to be extracted from the DICOM metadata, so that QC logs and events can be properly associated with imaging visits.

#### Acceptance Criteria

1. WHEN extracting visit information, THE Image_Identifier_Lookup_Gear SHALL use PTID from subject.label or DICOM PatientID tag (0010,0020)
2. WHEN extracting visit date, THE Image_Identifier_Lookup_Gear SHALL use the DICOM AcquisitionDate tag (0008,0022) as the primary source
3. WHEN AcquisitionDate is not available, THE Image_Identifier_Lookup_Gear SHALL use the DICOM StudyDate tag (0008,0020) as a fallback
4. WHEN neither AcquisitionDate nor StudyDate is available, THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message
5. WHEN extracting modality information, THE Image_Identifier_Lookup_Gear SHALL use the DICOM Modality tag (0008,0060) from the image metadata
6. WHEN Modality tag is not available, THE Image_Identifier_Lookup_Gear SHALL use a configurable default modality from gear configuration
7. WHEN no modality is configured and the DICOM tag is missing, THE Image_Identifier_Lookup_Gear SHALL use "UNKNOWN" as the default modality
8. WHEN visit information is incomplete (missing PTID or date), THE Image_Identifier_Lookup_Gear SHALL fail with an appropriate error message
9. WHEN creating visit metadata structures, THE Image_Identifier_Lookup_Gear SHALL use ImageVisitMetadata class that extends from a base visit metadata class to support future datatype extensions

### Requirement 7: Transactional Event Capture

**User Story:** As a data platform administrator, I want a submission event to be logged for the image, so that I can track when the image was processed through the identifier lookup workflow.

#### Acceptance Criteria

1. WHEN the Image_Identifier_Lookup_Gear processes the input image file, THE Image_Identifier_Lookup_Gear SHALL create a submission event using VisitEventCapture
2. WHEN creating the submission event, THE Image_Identifier_Lookup_Gear SHALL use the DICOM AcquisitionDate (or StudyDate as fallback) as the event timestamp
3. WHEN creating the submission event, THE Image_Identifier_Lookup_Gear SHALL populate the event with center label, project label, gear name, and ImageVisitMetadata (PTID, date, modality)
4. WHEN creating the submission event, THE Image_Identifier_Lookup_Gear SHALL set the action to "submit" and datatype to "image"
5. WHEN creating the submission event, THE Image_Identifier_Lookup_Gear SHALL NOT include form-specific fields such as packet (not applicable to images)
6. WHEN event capture is not configured, THE Image_Identifier_Lookup_Gear SHALL skip event logging and continue processing
7. WHEN event capture fails, THE Image_Identifier_Lookup_Gear SHALL log the error but not fail the entire operation
8. WHEN the S3 bucket for event capture is not accessible, THE Image_Identifier_Lookup_Gear SHALL fail during initialization with an appropriate error message
9. WHEN creating event structures, THE Image_Identifier_Lookup_Gear SHALL use ImageVisitMetadata that extends from a base visit metadata class to ensure compatibility with the generalized event capture system

### Requirement 8: Error Handling and Reporting

**User Story:** As a data platform administrator, I want comprehensive error handling and reporting, so that I can diagnose and resolve issues with identifier lookups.

#### Acceptance Criteria

1. WHEN any error occurs during processing, THE Image_Identifier_Lookup_Gear SHALL record the error with appropriate context (file path, PTID, ADCID)
2. WHEN the gear completes, THE Image_Identifier_Lookup_Gear SHALL add QC metadata to the input file with validation state (PASS or FAIL)
3. WHEN the gear completes, THE Image_Identifier_Lookup_Gear SHALL add error information to the file's QC metadata using the FileErrorList format
4. WHEN the gear completes successfully, THE Image_Identifier_Lookup_Gear SHALL add a gear tag to the input file
5. WHEN multiple errors occur, THE Image_Identifier_Lookup_Gear SHALL collect and report all errors in the QC metadata

### Requirement 9: Configuration

**User Story:** As a data platform administrator, I want configurable gear parameters, so that I can control the behavior of identifier lookups for different environments and use cases.

#### Acceptance Criteria

1. THE Image_Identifier_Lookup_Gear SHALL accept a "database_mode" configuration parameter (prod/dev) for identifier repository selection
2. THE Image_Identifier_Lookup_Gear SHALL accept a "naccid_field_name" configuration parameter for the subject metadata field name (default: "naccid")
3. THE Image_Identifier_Lookup_Gear SHALL accept a "default_modality" configuration parameter for use when DICOM Modality tag is missing (default: "UNKNOWN")
4. THE Image_Identifier_Lookup_Gear SHALL accept an "event_environment" configuration parameter for event capture environment prefix
5. THE Image_Identifier_Lookup_Gear SHALL accept an "event_bucket" configuration parameter for S3 bucket name for event storage
6. THE Image_Identifier_Lookup_Gear SHALL accept an "admin_group" configuration parameter for the NACC admin group ID (default: "nacc")
7. WHEN event_environment and event_bucket are both provided, THE Image_Identifier_Lookup_Gear SHALL enable event capture
8. WHEN either event_environment or event_bucket is missing, THE Image_Identifier_Lookup_Gear SHALL disable event capture

### Requirement 10: Generalized Metadata Architecture

**User Story:** As a developer, I want a generalized metadata architecture that supports multiple datatypes, so that the system can be extended to support future data types beyond forms and images.

#### Acceptance Criteria

1. THE Image_Identifier_Lookup_Gear SHALL use a base VisitMetadata class that defines common fields across all datatypes (PTID, date)
2. THE Image_Identifier_Lookup_Gear SHALL implement ImageVisitMetadata as a datatype-specific subclass of the base VisitMetadata class
3. WHEN ImageVisitMetadata is defined, THE Image_Identifier_Lookup_Gear SHALL include image-specific fields (modality) in addition to base fields
4. THE Image_Identifier_Lookup_Gear SHALL NOT include form-specific fields (packet, module) in ImageVisitMetadata
5. WHEN passing metadata to shared utilities (QCStatusLogManager, FileVisitAnnotator, VisitEventCapture), THE Image_Identifier_Lookup_Gear SHALL use the ImageVisitMetadata subclass
6. WHEN shared utilities process metadata, THE Image_Identifier_Lookup_Gear SHALL ensure they can handle both base VisitMetadata and datatype-specific subclasses polymorphically
7. THE Image_Identifier_Lookup_Gear SHALL design the metadata architecture to allow future addition of new datatype-specific subclasses (e.g., GenomicVisitMetadata, BiospecimenVisitMetadata) without modifying existing code

### Requirement 11: Idempotency and Skip Logic

**User Story:** As a data platform administrator, I want the gear to handle re-runs gracefully, so that processing the same image file multiple times does not cause errors or duplicate work.

#### Acceptance Criteria

1. WHEN the NACCID field already exists in subject.info with the correct value, THE Image_Identifier_Lookup_Gear SHALL skip the lookup and update operations
2. WHEN skipping due to existing NACCID, THE Image_Identifier_Lookup_Gear SHALL still create/update the QC status log with PASS status
3. WHEN skipping due to existing NACCID, THE Image_Identifier_Lookup_Gear SHALL still capture the submission event (if event capture is enabled)
4. WHEN the NACCID field exists with a different value, THE Image_Identifier_Lookup_Gear SHALL treat this as an error condition
5. WHEN the gear has already been run on the input file (indicated by gear tag), THE Image_Identifier_Lookup_Gear SHALL still process the file to ensure consistency

### Requirement 12: Code Reuse and Refactoring

**User Story:** As a developer, I want to maximize reuse of existing code and refactor shared functionality into common packages, so that the codebase remains maintainable and consistent across gears.

#### Acceptance Criteria

1. WHEN implementing the Image_Identifier_Lookup_Gear, THE Image_Identifier_Lookup_Gear SHALL reuse existing code from the `common/` package wherever possible
2. WHEN implementing identifier lookup functionality, THE Image_Identifier_Lookup_Gear SHALL reuse the IdentifiersLambdaRepository and related classes from the identifier lookup gear
3. WHEN implementing QC status logging, THE Image_Identifier_Lookup_Gear SHALL reuse QCStatusLogManager, FileVisitAnnotator, and related utilities from existing gears
4. WHEN implementing event capture, THE Image_Identifier_Lookup_Gear SHALL reuse VisitEventCapture, VisitEventLogger, and related utilities from existing gears
5. WHEN implementing Flywheel interactions, THE Image_Identifier_Lookup_Gear SHALL reuse ProjectAdaptor, SubjectAdaptor, and other adaptor classes from the `common/` package
6. WHEN shared functionality is found in gear-specific directories, THE Image_Identifier_Lookup_Gear MAY refactor it into the `common/` package if it benefits multiple gears
7. WHEN refactoring code from gear directories to common packages, THE Image_Identifier_Lookup_Gear SHALL ensure no existing functionality breaks by running all affected tests
8. WHEN creating new abstractions (e.g., ImageVisitMetadata), THE Image_Identifier_Lookup_Gear SHALL place them in appropriate common package modules for reuse by future gears
9. WHEN modifying existing shared utilities to support images, THE Image_Identifier_Lookup_Gear SHALL maintain backward compatibility with form-based usage
10. THE Image_Identifier_Lookup_Gear SHALL modify the existing template code in `gear/image_identifier_lookup` rather than creating a new gear from scratch
