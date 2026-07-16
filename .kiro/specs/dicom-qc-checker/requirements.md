# Requirements Document

## Introduction

The dicom-qc-checker gear is a Flywheel gear that evaluates the pass/fail status of a file based on its DICOM QC metadata and applies a corresponding tag. After a dicom-qc gear run, each file has QC results stored at `file.info.qc.dicom-qc`. This gear reads those results, determines overall pass/fail status, and tags the file accordingly using the project's standard `GearTags` pattern.

## Glossary

- **Gear**: A Flywheel gear (containerized processing unit) that operates on files within the Flywheel platform
- **DICOM_QC_Metadata**: The dictionary stored at `file.info.qc.dicom-qc` on a Flywheel file entry, containing check results from a prior dicom-qc gear run
- **Check_Result**: A dictionary entry within DICOM_QC_Metadata (excluding `job_info`) that contains a `state` field with value `"PASS"` or `"FAIL"`
- **Job_Info**: The entry keyed by `job_info` within DICOM_QC_Metadata that holds gear run metadata and is not a check result
- **GearTags**: A class from `nacc_common.error_models` that generates standardized pass/fail tags for a named gear
- **File_Entry**: A Flywheel SDK file object representing a file stored in the platform, with metadata and tags
- **Overall_Status**: The aggregate pass/fail determination for the file: FAIL if any Check_Result has state FAIL, PASS if all Check_Results have state PASS

## Requirements

### Requirement 1: Read DICOM QC Metadata

**User Story:** As a data pipeline operator, I want the gear to read the DICOM QC metadata from the input file, so that the pass/fail status can be evaluated.

#### Acceptance Criteria

1. WHEN the Gear receives an input File_Entry, THE Gear SHALL retrieve the DICOM_QC_Metadata from `file.info.qc.dicom-qc` on that file, where the metadata is a dictionary containing a `job_info` key (excluded from check evaluation) and zero or more check-result keys each holding a dictionary with a `state` field set to `"PASS"` or `"FAIL"`
2. IF the `file.info.qc.dicom-qc` key is absent or its value is an empty dictionary, THEN THE Gear SHALL log a warning message indicating no DICOM QC results are available for the file and exit with exit code 0
3. IF the `file.info.qc.dicom-qc` value is present but contains no check-result keys (only `job_info`), THEN THE Gear SHALL log a warning message indicating no DICOM QC check results are available and exit with exit code 0

### Requirement 2: Determine Overall QC Status

**User Story:** As a data pipeline operator, I want the gear to determine overall pass/fail status from individual check results, so that downstream processes can act on a single status indicator.

#### Acceptance Criteria

1. WHEN evaluating DICOM_QC_Metadata, THE Gear SHALL exclude the Job_Info entry from status evaluation
2. WHEN evaluating DICOM_QC_Metadata, THE Gear SHALL treat each remaining dictionary entry that contains a `state` field as a Check_Result
3. WHEN any Check_Result has `state` equal to `"FAIL"`, THE Gear SHALL determine the Overall_Status as FAIL
4. WHEN all Check_Results have `state` equal to `"PASS"`, THE Gear SHALL determine the Overall_Status as PASS
5. IF DICOM_QC_Metadata contains no Check_Results after excluding Job_Info, THEN THE Gear SHALL determine the Overall_Status as FAIL
6. IF any Check_Result has a `state` value that is neither `"PASS"` nor `"FAIL"`, THEN THE Gear SHALL determine the Overall_Status as FAIL

### Requirement 3: Log Failed Checks

**User Story:** As a data pipeline operator, I want the gear to log which specific checks failed, so that I can identify issues without inspecting metadata manually.

#### Acceptance Criteria

1. WHEN the Overall_Status is FAIL, THE Gear SHALL log at WARNING level the key name of each Check_Result entry whose `state` equals `"FAIL"`, excluding the `job_info` entry
2. IF the Overall_Status is FAIL due to an unrecognized `state` value, THEN THE Gear SHALL log a WARNING indicating which Check_Result has an invalid state value

### Requirement 4: Tag File with Status

**User Story:** As a data pipeline operator, I want the gear to tag the file with its pass/fail status, so that downstream gears and rules can filter files by QC outcome.

#### Acceptance Criteria

1. THE Gear SHALL use a GearTags instance initialized with gear name `"dicom-qc-checker"` for tag management
2. WHEN the Overall_Status has been determined, THE Gear SHALL remove any existing pass tag (`dicom-qc-checker-PASS`) and any existing fail tag (`dicom-qc-checker-FAIL`) from the File_Entry's tag list before adding the new status tag
3. WHEN the Overall_Status is PASS, THE Gear SHALL add the tag `dicom-qc-checker-PASS` to the File_Entry and persist the updated tag list to the Flywheel platform
4. WHEN the Overall_Status is FAIL, THE Gear SHALL add the tag `dicom-qc-checker-FAIL` to the File_Entry and persist the updated tag list to the Flywheel platform
5. IF persisting the updated tags to the Flywheel platform fails, THEN THE Gear SHALL log an error message indicating the tag update failure and exit with a failure status code

### Requirement 5: Gear Configuration

**User Story:** As a platform administrator, I want the gear to follow standard Flywheel gear conventions, so that it integrates with the existing platform infrastructure.

#### Acceptance Criteria

1. THE Gear manifest SHALL declare a single file input with base type `"file"` and an `api-key` input with base type `"api-key"`
2. THE Gear SHALL use the gear name `"dicom-qc-checker"` in its manifest
3. THE Gear SHALL use the Python package name `dicom_qc_checker_app` for its application code
4. THE Gear SHALL follow the standard gear directory layout: `gear/dicom_qc_checker/src/docker/`, `gear/dicom_qc_checker/src/python/dicom_qc_checker_app/`, `gear/dicom_qc_checker/test/python/`
5. THE Gear manifest SHALL include the required fields: `name`, `label`, `description`, `version`, `author`, `license`, `command`, and `custom.gear-builder.image` with the image tag matching the manifest version
