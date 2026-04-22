# Image Identifier Lookup

The image-identifier-lookup gear performs NACCID lookups for DICOM images uploaded to the NACC Data Platform. The gear processes a DICOM image file (or a zip archive containing DICOM files), extracts patient identifiers from the DICOM metadata, queries the identifier database, and updates the Flywheel subject metadata with the corresponding NACCID.

## Overview

This gear is designed to run on individual DICOM image files as they are uploaded to the platform. It:

- Extracts patient identifiers (PTID) from the subject metadata or DICOM file
- Retrieves the center identifier (ADCID) from the project pipeline configuration
- Performs identifier lookup against the NACC database
- Updates the subject metadata with the NACCID and DICOM metadata
- Creates QC status logs for tracking
- Captures visit events for submission tracking

On re-runs where the NACCID and DICOM metadata are already stored in subject custom info, the gear skips opening the DICOM file entirely.

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

- **`event_environment`** (string, required): Environment for visit event capture
  - Valid values: `"prod"` or `"dev"`
  - Determines the environment prefix used when storing events in S3

- **`event_bucket`** (string, required): S3 bucket name for event capture
  - The gear must have write access to this bucket

- **`apikey_path_prefix`** (string, default: "/prod/flywheel/gearbot"): AWS SSM parameter path prefix for API keys

## Input

The gear requires a single DICOM image file as input:

- **`input_file`**: A DICOM format image file or a zip archive containing DICOM files
  - Must be a valid DICOM file with standard DICOM tags, or a zip archive containing one
  - The file type must be `dicom` in Flywheel
  - When a zip archive is provided, the gear extracts the first DICOM file (by `.dcm`/`.dicom` extension, or extensionless files)

The gear extracts the following information:

1. **PTID (Patient ID)**: Retrieved from either:
   - Subject label (preferred)
   - DICOM PatientID tag (0010,0020) as fallback

2. **ADCID (Center ID)**: Retrieved from the project's pipeline configuration

3. **Study Date**: Retrieved from DICOM StudyDate tag (0008,0020)

4. **Modality**: Retrieved from DICOM Modality tag (0008,0060)

## Processing Flow

1. **Initialization**: Validates that event capture is configured (both `event_environment` and `event_bucket` must be provided)

2. **Custom Info Extraction**: Extracts available data from Flywheel metadata:
   - Pipeline ADCID from project custom info
   - PTID from subject label
   - Existing NACCID from subject custom info
   - Study date and modality from previously stored `dicom_metadata` in subject custom info (if available from a prior run)

3. **Short-Circuit Check**: If PTID, study date, and modality are all available from custom info, the gear skips opening the DICOM file. This avoids unnecessary file I/O on re-runs.

4. **File Resolution** (if needed): If any required data is missing from custom info, the gear opens the input file. If the input is a zip archive, it extracts the first DICOM file to a temporary location.

5. **DICOM Enrichment** (if needed): Fills in missing fields (PTID, study date, modality) from the DICOM file and builds visit metadata.

6. **Idempotency Check**: If the subject already has a NACCID in metadata, the gear skips the lookup step.

7. **Identifier Lookup**: Queries the identifier database with ADCID and PTID to retrieve the NACCID.

8. **Metadata Update**: Updates the subject metadata with the NACCID and comprehensive DICOM metadata (unless in dry run mode).

9. **QC Logging**: Creates a QC status log file at the project level.

10. **Event Capture**: Logs a submission event to S3 for tracking.

11. **File Tagging**: Adds QC metadata and gear tags to the processed file.

## Output

The gear produces the following outputs:

### Subject Metadata Update

The subject's metadata is updated with the NACCID and DICOM metadata (unless in dry run mode):

```json
{
  "naccid": "NACC123456",
  "dicom_metadata": {
    "patient_id": "110001",
    "study_date": "20240115",
    "modality": "MR",
    "study_instance_uid": "1.2.840.113619.2.1.1.1",
    "series_instance_uid": "1.2.840.113619.2.1.1.2",
    "series_number": "5",
    "manufacturer": "Siemens",
    "manufacturer_model_name": "Skyra",
    "series_description": "T1 MPRAGE",
    "magnetic_field_strength": "3.0",
    "images_in_acquisition": "176"
  }
}
```

### QC Status Log

A project-level log file is created with the naming pattern:
- `{ptid}_{date}_{modality}_qc-status.log`

Example: `12345_2024-03-15_MR_qc-status.log`

### File Metadata and Tagging

After processing, the gear updates the input DICOM file with the following metadata. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

1. **QC Result**: A validation QC result is added to the file with:
   - `name`: `"validation"`
   - `state`: `"PASS"` or `"FAIL"` depending on processing outcome
   - `data`: Error details (from `FileErrorList`) if any errors occurred

2. **Validation Timestamp**: The file's `.info` metadata is updated with a `validated_timestamp` field set to the current UTC time. This allows tracking when the file was last processed.

3. **Gear Tags**: The file is tagged using the `GearTags` mechanism:
   - Adds `gear-PASS` or `gear-FAIL` tag (prefixed with the gear name) based on processing status
   - Previous gear status tags are replaced

Note: Failures in metadata updates are logged but do not fail the gear, as these updates are considered non-critical.

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
- Missing required DICOM tags (StudyDate, Modality)
- Zip archive containing no DICOM files

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

## Integration with Other Gears

This gear is typically used in conjunction with:

- **Project Management**: Sets up projects with pipeline ADCID configuration
- **Identifier Provisioning**: Provisions new NACCIDs when needed
- **Form Processing Gears**: Uses the same QC logging and event capture infrastructure

## Technical Details

### DICOM Tags Extracted

| Tag | Name | Purpose |
|-----|------|---------|
| `(0010,0020)` | PatientID | Patient identifier (PTID fallback) |
| `(0008,0020)` | StudyDate | Date of the study |
| `(0008,0060)` | Modality | Imaging modality (MR, CT, PET, etc.) |
| `(0020,000D)` | StudyInstanceUID | Unique study identifier |
| `(0020,000E)` | SeriesInstanceUID | Unique series identifier |
| `(0020,0011)` | SeriesNumber | Series number within study |
| `(0008,0021)` | SeriesDate | Date of the series |
| `(0018,0087)` | MagneticFieldStrength | Scanner field strength |
| `(0008,0070)` | Manufacturer | Scanner manufacturer |
| `(0008,1090)` | ManufacturerModelName | Scanner model |
| `(0008,103E)` | SeriesDescription | Series description |
| `(0020,1002)` | ImagesInAcquisition | Number of images |

### Dependencies

- `pydicom`: DICOM file parsing
- `flywheel-sdk`: Flywheel platform integration
- `fw-gear`: Gear development framework
- `boto3`: AWS S3 and SSM integration
- `pydantic`: Data validation for LookupContext model

### Architecture

The gear follows a clean architecture pattern:

- `run.py`: Gear interface, Flywheel context management, file resolution, and DICOM extraction
- `main.py`: `ImageIdentifierLookup` class orchestrating the lookup workflow
- `processor.py`: Business logic for identifier lookup and subject metadata updates
- `extraction.py`: `LookupContext` model for accumulating workflow data, DICOM metadata extraction
- `file_resolver.py`: Zip archive detection and DICOM file extraction
- `dicom_utils.py`: Low-level DICOM tag reading via pydicom
