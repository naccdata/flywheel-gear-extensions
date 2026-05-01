# Pipeline Event Logger

The pipeline-event-logger gear bridges upstream pipeline gears (which write QC results to file metadata via Flywheel's `context.metadata.add_qc_result`) and NACC's project-level QC status logging and S3 event capture systems. It reads QC outcomes from the input file's metadata, updates the project-level QC status log attributing the entry to the upstream gear, and optionally captures a `VisitEvent` to the S3 transaction log.

## Overview

This gear is designed for pipelines where upstream gears process files and write QC results to file metadata but have no knowledge of NACC's QC status logs or event capture infrastructure. It runs after an upstream gear completes and:

- Reads the upstream gear's QC outcome from `file.info.qc.{upstream_gear_name}`
- Reads visit/file identification from `file.info.data_identification`
- Updates the project-level QC status log, attributed to the upstream gear
- Optionally captures a `VisitEvent` to the S3 transaction log based on the QC outcome

The gear attributes all QC log entries and events to the upstream gear name, not to itself. This is critical because downstream systems key on gear name.

## Prerequisites

### Input File Metadata

The input file **must** have the following metadata written by an upstream gear or earlier pipeline stage:

1. **`file.info.qc.{upstream_gear_name}`** — QC results written via `context.metadata.add_qc_result`. This is the standard Flywheel QC metadata convention. The expected structure is:

   ```json
   {
     "job_info": { "job_id": "...", "version": "...", "config": {...}, "inputs": {...} },
     "<check_name>": {
       "state": "PASS | FAIL | IN REVIEW",
       "<data_key>": [... gear-specific error objects ...]
     }
   }
   ```

   A gear may write multiple check results (e.g., `dicom-validator`, `jsonschema-validation`). The aggregate status is derived using priority: FAIL > IN REVIEW > PASS.

2. **`file.info.data_identification`** — A serialized `DataIdentification` dict identifying the visit/file. This is used to generate QC log filenames and create events.

   The expected structure is a flat dict with these fields:

   | Field | Type | Required | Description |
   |-------|------|----------|-------------|
   | `ptid` | string | Yes | Participant ID (center-assigned) |
   | `adcid` | int | Yes | Center identifier |
   | `date` | string | Yes | Visit or collection date (YYYY-MM-DD) |
   | `module` | string | One of module/modality | Form module (UDS, LBD, FTLD, NP, etc.) |
   | `modality` | string | One of module/modality | Imaging modality (MR, CT, PET, etc.) |
   | `visitnum` | string | No | Visit sequence number |

   Example for a form file:

   ```json
   {
     "ptid": "110001",
     "adcid": 42,
     "date": "2024-06-15",
     "module": "UDS",
     "visitnum": "1"
   }
   ```

   Example for an imaging file:

   ```json
   {
     "ptid": "110001",
     "adcid": 42,
     "date": "2024-06-15",
     "modality": "MR"
   }
   ```

**Important**: This gear does **not** construct `DataIdentification` from other metadata sources (e.g., `file.info.visit`, `file.info.forms.json`, or the Flywheel hierarchy). The upstream gear or an earlier pipeline stage is responsible for writing `file.info.data_identification`. If your pipeline does not produce this metadata, this gear cannot be used without modification to the upstream pipeline.

## Environment

This gear uses the AWS SSM parameter store for API key management and S3 for event capture. It expects that AWS credentials are available in environment variables within the Flywheel runtime:

- `AWS_SECRET_ACCESS_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_DEFAULT_REGION`

The gear needs to be added to the allow list for these variables to be shared.

## Configuration

Gear configs are defined in [manifest.json](../../gear/pipeline_event_logger/src/docker/manifest.json).

### Configuration Parameters

- **`upstream_gear_name`** (string, required): Name of the upstream gear whose QC results to read from `file.info.qc`. This must match the gear name used by the upstream gear when writing QC metadata.

- **`error_configs`** (list of objects, optional): Describes how to extract errors from the upstream gear's QC check results. Each entry targets a specific check result and maps its gear-specific error fields to the standard `FileError` model used by the QC status log.

  If not provided, the QC status log receives an empty error list (status is still recorded).

  Each entry has:

  | Field | Type | Required | Description |
  |-------|------|----------|-------------|
  | `check_name` | string | Yes | Name of the check result to read (e.g., `"dicom-validator"`, `"validation"`) |
  | `data_key` | string | No (default: `"data"`) | Key within the check result holding the error list |
  | `field_mapping` | object | Yes | Maps source error fields to `FileError` fields |

  The `field_mapping` object:

  | Field | Type | Required | Description |
  |-------|------|----------|-------------|
  | `message` | string | Yes | Source key for the error message |
  | `error_type` | string | No (default: `"error"`) | Source key or literal for error type (`"error"`, `"warning"`, `"alert"`) |
  | `error_code` | string | No (default: `"qc-error"`) | Source key or literal for error code |
  | `value` | string | No | Source key for the offending value (optional) |

  **Field resolution**: Each mapping value is first checked as a key in the source error object. If the key exists, the value from the source is used. Otherwise, the mapping value is treated as a literal string.

  Example for a DICOM QC gear with two check types:

  ```json
  {
    "error_configs": [
      {
        "check_name": "dicom-validator",
        "field_mapping": {
          "message": "name",
          "error_code": "dicom-validation"
        }
      },
      {
        "check_name": "jsonschema-validation",
        "field_mapping": {
          "message": "error_message",
          "error_type": "error_type",
          "error_code": "jsonschema-validation"
        }
      }
    ]
  }
  ```

  In this example:
  - For `dicom-validator`: each error object has a `"name"` key, so `message` resolves to `source["name"]`. `"dicom-validation"` is not a key in the source, so it's used as a literal error code.
  - For `jsonschema-validation`: both `"error_message"` and `"error_type"` are keys in the source objects, so they resolve to the source values.

- **`event_actions`** (object, optional): Maps QC outcome keys to event action strings. If empty or not provided, no events are captured.

  Valid outcome keys: `"pass"`, `"fail"`, `"in-review"`

  Example:

  ```json
  {
    "pass": "pass-qc",
    "fail": "not-pass-qc"
  }
  ```

  Any outcome not present in the map produces no event. This allows selective event capture (e.g., only capture events on failure).

- **`event_environment`** (string, optional): Environment for event capture. Required if `event_actions` is non-empty.
  - Valid values: `"prod"` or `"dev"`

- **`event_bucket`** (string, optional): S3 bucket name for event capture. Required if `event_actions` is non-empty.

- **`apikey_path_prefix`** (string, default: "/prod/flywheel/gearbot"): AWS SSM parameter path prefix for the gearbot API key.

- **`dry_run`** (boolean, default: false): Skip all write operations (QC log update and event capture). The gear still reads and validates QC metadata and data identification, which is useful for testing pipeline configuration.

## Input

- **`input_file`**: The file processed by the upstream gear. Must have `file.info.qc.{upstream_gear_name}` and `file.info.data_identification` populated.

## Processing Flow

1. **Read GearQC**: Reads `file.info.qc.{upstream_gear_name}` and constructs a `GearQC` object representing all check results for the upstream gear. Derives the aggregate QC status (PASS, FAIL, or IN REVIEW) using priority ordering: FAIL > IN REVIEW > PASS. Fails if missing or invalid.

2. **Extract Errors**: If `error_configs` is provided, extracts errors from the targeted check results using the configured field mappings. Each matching check result's `data` (or configured `data_key`) is parsed into `FileError` objects. If no config is provided, an empty error list is used.

3. **Read Data Identification**: Reads `file.info.data_identification` and deserializes via `DataIdentification.from_visit_metadata()`. Fails if missing or invalid.

4. **Resolve Timestamp**: Uses `file.info.validated-timestamp` if present, otherwise falls back to `file.modified`.

5. **Update QC Status Log** (non-critical): Updates the project-level QC status log with the visit identification, upstream gear name, QC status, and errors. Failures are logged as warnings.

6. **Capture Event** (non-critical): If event capture is configured and the QC outcome has a matching action in `event_actions`, creates and captures a `VisitEvent` to S3. Failures are logged as warnings.

## Output

### QC Status Log

A project-level QC status log file is created or updated, attributed to the upstream gear name. The log filename is derived from the `DataIdentification` (participant, date, module/modality).

### Event Capture

When configured, the gear writes a `VisitEvent` JSON file to the S3 transaction log bucket. The event includes:

- Action (from `event_actions` mapping)
- Visit metadata (from `DataIdentification`)
- Completion timestamp
- Upstream gear name

## Error Handling

The gear distinguishes between critical and non-critical failures:

### Critical Failures (gear terminates)

- Input file cannot be retrieved from Flywheel
- Parent project cannot be found
- `file.info.qc.{upstream_gear_name}` is missing or invalid
- No check results with a valid state found for the upstream gear
- `file.info.data_identification` is missing or invalid
- `event_actions` is non-empty but `event_environment` or `event_bucket` is missing
- `error_configs` is present but fails validation (malformed config)

### Non-Critical Failures (warning logged, gear continues)

- QC status log update fails
- Event creation returns None (invalid project label)
- Event capture to S3 fails

The rationale: the upstream gear's QC result is already safely stored in `file.info.qc`. The QC log and event capture are downstream propagation steps that can be retried independently.

## Usage Examples

### Imaging Pipeline (with event capture and error extraction)

```json
{
  "upstream_gear_name": "dicom-qc",
  "error_configs": [
    {
      "check_name": "dicom-validator",
      "field_mapping": {
        "message": "name",
        "error_code": "dicom-validation"
      }
    },
    {
      "check_name": "jsonschema-validation",
      "field_mapping": {
        "message": "error_message",
        "error_type": "error_type",
        "error_code": "jsonschema-validation"
      }
    }
  ],
  "event_actions": {
    "pass": "pass-qc",
    "fail": "not-pass-qc"
  },
  "event_environment": "prod",
  "event_bucket": "nacc-event-logs",
  "dry_run": false
}
```

### Form Pipeline (NACC gears with FileError convention)

For upstream gears that write `FileError` lists to `validation.data` (the NACC convention), the field mapping matches the `FileError` model directly:

```json
{
  "upstream_gear_name": "form-qc-checker",
  "error_configs": [
    {
      "check_name": "validation",
      "field_mapping": {
        "message": "message",
        "error_type": "type",
        "error_code": "code"
      }
    }
  ],
  "event_actions": {
    "pass": "pass-qc",
    "fail": "not-pass-qc"
  },
  "event_environment": "prod",
  "event_bucket": "nacc-event-logs"
}
```

### QC Logging Only (no error extraction, no event capture)

When you only need to record the pass/fail status without detailed errors:

```json
{
  "upstream_gear_name": "image-validator",
  "dry_run": false
}
```

### Dry Run for Testing

```json
{
  "upstream_gear_name": "dicom-qc",
  "error_configs": [
    {
      "check_name": "dicom-validator",
      "field_mapping": {
        "message": "name",
        "error_code": "dicom-validation"
      }
    }
  ],
  "event_actions": {
    "pass": "pass-qc",
    "fail": "not-pass-qc"
  },
  "event_environment": "dev",
  "event_bucket": "nacc-event-logs-dev",
  "dry_run": true
}
```

## Integration Notes

### Upstream Gear Requirements

For this gear to work, the upstream gear (or an earlier pipeline stage) must:

1. Write QC results using `context.metadata.add_qc_result` (standard Flywheel convention)
2. Write a serialized `DataIdentification` to `file.info.data_identification`

### Pipelines Where This Gear Cannot Be Used Directly

- **Form pipeline (visit-based)**: Form gears currently write identification to `file.info.visit` or `file.info.forms.json`, not to `file.info.data_identification`. To use this gear with form pipelines, the upstream gear or a preceding pipeline stage would need to be modified to also write `file.info.data_identification`.

### Related Gears

- **image_identifier_lookup**: Similar QC logging and event capture pattern for imaging. Performs identifier lookup and writes subject metadata.
- **form_qc_checker**: Form QC processing with built-in NACC logging (does not need this gear).
- **form_scheduler**: Form event capture via `event_accumulator` (does not need this gear).

## Architecture

The gear follows the standard NACC gear architecture:

- `run.py`: Flywheel context management, dependency initialization, file/project retrieval, config parsing
- `main.py`: Business logic — reads `GearQC`, extracts errors via config, updates QC log, captures events
- `qc_reader.py`: Generic QC metadata reader — `GearQC`, `GearQCResult`, `QCErrorConfig`, and `ErrorFieldMapping` models

The `qc_reader` module is intentionally independent of form-specific models (`FileQCModel`). It handles the general Flywheel QC convention where check results have a `state` field and gear-specific data. The `error_configs` mechanism allows the gear to extract errors from any upstream gear without hard-coding assumptions about the error structure.

All write operations (QC log, event capture) are wrapped in try/except blocks. The gear's core value is propagating QC results to NACC infrastructure; if a propagation step fails, the upstream QC result remains safely in `file.info.qc`.
