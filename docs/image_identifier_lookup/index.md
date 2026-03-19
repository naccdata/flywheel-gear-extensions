# Image Identifier Lookup

The image-identifier-lookup gear performs NACCID lookups for DICOM images uploaded to the NACC Data Platform. The gear processes a single DICOM image file, extracts patient identifiers from the DICOM metadata, queries the identifier database, and updates the Flywheel subject metadata with the corresponding NACCID.

## Overview

This gear is designed to run on individual DICOM image files as they are uploaded to the platform. It:

- Extracts patient identifiers (PTID) from the DICOM file or subject metadata
- Retrieves the center identifier (ADCID) from the project pipeline configuration
- Performs identifier lookup against the NACC database
- Updates the subject metadata with the NACCID
- Creates QC status logs for tracking
- Captures visit events for submission tracking

## Environment

This gear uses the AWS SSM parameter store for API key management and S3 for event capture. It expects that AWS credentials are available in environment variables within the Flywheel runtime:

- `AWS_SECRET_ACCESS_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_DEFAULT_REGION`

The gear needs to be added to the allow list for these variables to be shared.

## Configuration

Gear configs are defined in [manifest.json](../../gear/image_identifier_lookup/src/docker/manifest.json).

### Configuration Parameters

- **`dry_run`** (boolean, default: false): Whether to perform a dry run without making changes
  - `true`: Performs all lookups and validations but does not update subject metadata
  - `false`: Updates subject metadata with the looked-up NACCID

- **`database_mode`** (string, default: "prod"): Which identifier database to query
  - `"prod"`: Query the production identifier database
  - `"dev"`: Query the development identifier database

- **`naccid_field_name`** (string, default: "naccid"): Field name for storing NACCID in subject metadata
  - Allows customization of the metadata field name if needed

- **`default_modality`** (string, default: "UNKNOWN"): Default modality to use when DICOM Modality tag is missing
  - Used as fallback when the DICOM file does not contain a Modality tag (0008,0060)

- **`event_environment`** (string, required for event capture): Environment for visit event capture
  - Valid values: `"prod"` or `"dev"`
  - Determines the environment prefix used when storing events in S3
  - Required when `event_bucket` is configured

- **`event_bucket`** (string, required for event capture): S3 bucket name for event capture
  - The gear must have write access to this bucket
  - Required when `event_environment` is configured

- **`admin_group`** (string, default: "nacc"): Name of the NACC admin group
  - Used for permission checks and administrative operations

- **`apikey_path_prefix`** (string, default: "/prod/flywheel/gearbot"): AWS SSM parameter path prefix for API keys
  - Instance-specific path for retrieving gearbot API keys from SSM

## Input

The gear requires a single DICOM image file as input:

- **`input_file`**: A DICOM format image file
  - Must be a valid DICOM file with standard DICOM tags
  - The file type must be `dicom` in Flywheel

The gear extracts the following information:

1. **PTID (Patient ID)**: Retrieved from either:
   - Subject label (if set)
   - DICOM PatientID tag (0010,0020) as fallback

2. **ADCID (Center ID)**: Retrieved from the project's pipeline configuration

3. **Study Date**: Retrieved from DICOM StudyDate tag (0008,0020)

4. **Modality**: Retrieved from DICOM Modality tag (0008,0060), or uses `default_modality` if missing

## Processing Flow

1. **Initialization**: Validates that event capture is configured (both `event_environment` and `event_bucket` must be provided)

2. **Data Extraction**: Extracts identifiers and metadata from DICOM file and Flywheel containers

3. **Idempotency Check**: If the subject already has a NACCID in metadata, the gear skips lookup and succeeds

4. **Identifier Lookup**: Queries the identifier database with ADCID and PTID to retrieve the NACCID

5. **Metadata Update**: Updates the subject metadata with the NACCID (unless in dry run mode)

6. **QC Logging**: Creates a QC status log file at the project level with format:
   - `{ptid}_{date}_{modality}_qc-status.log`

7. **Event Capture**: Logs a submission event to S3 for tracking

8. **File Tagging**: Adds QC metadata and gear tags to the processed file

## Output

The gear produces the following outputs:

### Subject Metadata Update

The subject's metadata is updated with the NACCID field (unless in dry run mode):

```json
{
  "naccid": "NACC123456"
}
```

### QC Status Log

A project-level log file is created with the naming pattern:
- `{ptid}_{date}_{modality}_qc-status.log`

Example: `12345_2024-03-15_MR_qc-status.log`

### File Metadata

The processed DICOM file receives QC metadata tags indicating processing status and any errors encountered.

### Event Capture

When event capture is configured, the gear creates a submission event in the configured S3 bucket. Events include:

- Visit metadata (center, project, date)
- Image metadata (modality, study information)
- Processing status and timestamps

Event capture failures do not affect the primary identifier lookup functionality.

## Error Handling

The gear implements comprehensive error handling:

### Validation Errors

- Missing PTID (neither subject label nor DICOM PatientID available)
- Missing or invalid pipeline ADCID in project metadata
- Invalid DICOM file format
- Missing required DICOM tags

### Lookup Errors

- NACCID not found for the given PTID/ADCID combination
- Database connection failures
- API authentication failures

### Configuration Errors

- Missing event capture configuration (both `event_environment` and `event_bucket` required)
- Invalid database mode
- Invalid event environment

All errors are logged to:
- Gear execution logs
- QC status log files
- File metadata (QC tags)

## Usage Examples

### Standard Production Usage

```json
{
  "dry_run": false,
  "database_mode": "prod",
  "event_environment": "prod",
  "event_bucket": "nacc-event-logs"
}
```

### Development Testing

```json
{
  "dry_run": true,
  "database_mode": "dev",
  "event_environment": "dev",
  "event_bucket": "nacc-event-logs-dev"
}
```

### Custom NACCID Field

```json
{
  "dry_run": false,
  "database_mode": "prod",
  "naccid_field_name": "participant_naccid",
  "event_environment": "prod",
  "event_bucket": "nacc-event-logs"
}
```

## Integration with Other Gears

This gear is typically used in conjunction with:

- **Project Management**: Sets up projects with pipeline ADCID configuration
- **Identifier Provisioning**: Provisions new NACCIDs when needed
- **Form Processing Gears**: Uses the same QC logging and event capture infrastructure

## Technical Details

### DICOM Tags Used

- `(0010,0020)` - PatientID: Patient identifier
- `(0008,0020)` - StudyDate: Date of the study
- `(0008,0060)` - Modality: Imaging modality (MR, CT, PET, etc.)
- `(0020,000D)` - StudyInstanceUID: Unique study identifier
- `(0020,000E)` - SeriesInstanceUID: Unique series identifier
- `(0020,0011)` - SeriesNumber: Series number within study

### Dependencies

- `pydicom`: DICOM file parsing
- `flywheel-sdk`: Flywheel platform integration
- `fw-gear`: Gear development framework
- `boto3`: AWS S3 and SSM integration

### Architecture

The gear follows a clean architecture pattern:

- `run.py`: Gear interface and Flywheel context management
- `main.py`: Workflow orchestration
- `processor.py`: Business logic for identifier lookup
- `extraction.py`: Data extraction and validation
- `dicom_utils.py`: DICOM file utilities
- `errors.py`: Error handling and custom exceptions
