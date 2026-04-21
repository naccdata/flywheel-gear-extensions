# QC Metadata and Gear Tagging Conventions

This page documents the standard conventions used across NACC gears for recording quality control (QC) results in Flywheel file metadata and for tagging files with gear processing status.

These conventions originate from the [Flywheel QC metadata framework](https://docs.flywheel.io/) and are implemented in the `nacc_common.error_models` module.

## Overview

When a gear processes a file, it can record three types of metadata:

1. **QC Result** — structured validation data stored in `file.info.qc`
2. **Validation Timestamp** — when the file was last validated, stored in `file.info.validated_timestamp`
3. **Gear Tags** — status tags on the file indicating pass/fail for a specific gear

Not all gears use all three. The table in [Gear Usage Summary](#gear-usage-summary) shows which gears use which mechanisms.

## QC Result Metadata

QC results are stored in the file's `.info.qc` metadata using the Flywheel `add_qc_result` API. The structure follows a hierarchy of Pydantic models defined in `nacc_common.error_models`.

### Metadata Structure

```
file.info.qc
└── <gear-name>                    # GearQCModel
    └── validation                 # ValidationModel
        ├── state: "PASS" | "FAIL" | "IN REVIEW"
        ├── data: [FileError, ...]
        └── cleared: [ClearedAlertModel, ...]
```

### Data Models

#### `FileQCModel`

Top-level model at `file.info.qc`. Contains a dictionary of gear-specific QC data keyed by gear name.

- `qc`: `Dict[str, GearQCModel]` — maps gear names to their QC data
- `get_file_status()` — returns overall file status across all gears:
  - `"FAIL"` if any gear has status `"FAIL"`
  - `"IN REVIEW"` if no gear failed but at least one is `"IN REVIEW"`
  - `"PASS"` if all gears passed

#### `GearQCModel`

Per-gear QC data at `file.info.qc.<gear-name>`.

- `validation`: `ValidationModel` — the validation results for this gear

#### `ValidationModel`

Validation results at `file.info.qc.<gear-name>.validation`.

- `state`: `"PASS"` | `"FAIL"` | `"IN REVIEW"` — the QC status
- `data`: `List[FileError]` — list of errors found during validation
- `cleared`: `List[ClearedAlertModel]` — list of alerts that have been cleared by a user

#### `FileError`

Individual error record with the following fields:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `type` | `"alert"` \| `"error"` \| `"warning"` | Severity level |
| `code` | `str` | Error code (e.g., NACC data quality check code) |
| `message` | `str` | Human-readable error description |
| `timestamp` | `str` (optional) | When the error was generated |
| `location` | `CSVLocation` \| `JSONLocation` (optional) | Where in the file the error occurred |
| `container_id` | `str` (optional) | Flywheel container ID |
| `flywheel_path` | `str` (optional) | Flywheel path to the file |
| `value` | `str` (optional) | The value that caused the error |
| `expected` | `str` (optional) | The expected value |
| `ptid` | `str` (optional) | Participant ID |
| `visitnum` | `str` (optional) | Visit number |
| `date` | `str` (optional) | Visit date |
| `naccid` | `str` (optional) | NACC ID |

#### `ClearedAlertModel`

Represents an alert that has been reviewed and cleared by a user.

- `clear`: `bool` — whether the alert is cleared
- `finalized`: `bool` — whether the clearance is finalized
- `alertHash`: `str` — hash identifying the specific alert
- `provenance`: `List[ClearedAlertProvenance]` — audit trail of clearance actions

### How QC Results Are Written

Gears write QC results using the Flywheel gear context API:

```python
context.metadata.add_qc_result(
    file_input,
    name="validation",
    state="PASS",  # or "FAIL"
    data=errors.model_dump(by_alias=True) if errors else None,
)
```

### How QC Results Are Read

QC data can be read from a file entry using the factory method:

```python
from nacc_common.error_models import FileQCModel

qc_model = FileQCModel.create(file_entry)
status = qc_model.get_file_status()        # Overall status
gear_status = qc_model.get_status("form-qc-checker")  # Per-gear status
errors = qc_model.get_errors("form-qc-checker")        # Per-gear errors
```

## Validation Timestamp

Some gears record when a file was last validated by setting `file.info.validated_timestamp` to the current UTC time. This is used by downstream gears (e.g., `form-qc-coordinator`) to determine whether a file needs re-validation.

```python
from keys.keys import MetadataKeys
from nacc_common.form_dates import DEFAULT_DATE_TIME_FORMAT

timestamp = datetime.now(timezone.utc).strftime(DEFAULT_DATE_TIME_FORMAT)
context.metadata.update_file_metadata(
    file_input,
    container_type=context.config.destination["type"],
    info={MetadataKeys.VALIDATED_TIMESTAMP: timestamp},
)
```

## Gear Tags

Gear tags provide a quick visual indicator of whether a file passed or failed processing by a specific gear. Tags are managed by the `GearTags` class in `nacc_common.error_models`.

### Tag Format

Tags follow the pattern `{gear-name}-{STATUS}`:

- `form-qc-checker-PASS`
- `form-qc-checker-FAIL`
- `image-identifier-lookup-PASS`
- `image-identifier-lookup-FAIL`

### How Tags Work

The `GearTags` class ensures that only one status tag per gear exists on a file at any time. When updating, it removes any existing pass/fail tag for that gear before adding the new one:

```python
from nacc_common.error_models import GearTags

gear_tags = GearTags(gear_name="form-qc-checker")
updated_tags = gear_tags.update_tags(tags=file.tags, status="PASS")
# Removes "form-qc-checker-FAIL" if present, adds "form-qc-checker-PASS"

context.metadata.update_file_metadata(
    file_input,
    tags=updated_tags,
    container_type=context.config.destination["type"],
)
```

### Simple File Tags

Some gears add a simple tag with just the gear name (e.g., `"form-transformer"`, `"identifier-lookup"`) rather than using the `GearTags` pass/fail mechanism. This indicates the file has been processed by the gear without conveying pass/fail status through the tag itself. These gears still record pass/fail status in the QC result metadata.

## Gear Usage Summary

| Gear | QC Result | Validation Timestamp | Gear Tags (PASS/FAIL) | Simple Tag |
| ---- | :-------: | :------------------: | :-------------------: | :--------: |
| [form-qc-checker](../form_qc_checker/index.md) | ✓ | ✓ | ✓ | |
| [image-identifier-lookup](../image_identifier_lookup/index.md) | ✓ | ✓ | ✓ | |
| [form-qc-coordinator](../form_qc_coordinator/index.md) | | | ✓ (resets tags) | ✓ |
| [form-transformer](../form_transformer/index.md) | ✓ | | | ✓ |
| [csv-subject-splitter](../csv_subject_splitter/index.md) | ✓ | | | ✓ |
| [identifier-lookup](../identifier_lookup/index.md) | ✓ | | | ✓ |
| [form-screening](../form_screening/index.md) | ✓ (fail only) | | | queue tags |
| [identifier-provisioning](../identifier_provisioning/index.md) | ✓ | | | ✓ |
| [gather-form-data](../gather_form_data/index.md) | ✓ | | | ✓ |
| [gather-submission-status](../gather_submission_status/index.md) | ✓ | | | ✓ |

**Notes:**

- **form-qc-coordinator** uses `GearTags` to *reset* tags on visit files when re-triggering QC, rather than to set its own pass/fail status.
- **form-screening** only writes a QC result on failure. On success, it adds configurable queue tags (e.g., `"queued"`) to trigger downstream processing.
- Gears not listed in this table do not write QC metadata or gear tags to files.
