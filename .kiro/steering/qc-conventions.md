---
inclusion: fileMatch
fileMatchPattern: '**/qc_reader.py,**/error_models.py,**/run.py,**/main.py'
---

# QC Metadata Conventions

## Overview

NACC gears that write QC results to `file.info.qc.<gear_name>` must follow these conventions so that `pipeline-event-logger` can consistently read aggregate status and extract structured errors without per-gear special-casing.

## QC Result Structure

Each gear writes one or more **check results** under its QC namespace, plus a `job_info` metadata entry:

```json
{
  "job_info": { ... },
  "<check_name>": {
    "state": "PASS" | "FAIL" | "IN REVIEW",
    "data": <list of error dicts> | null
  }
}
```

### Rules

1. **`state`** — Required. Must be one of `"PASS"`, `"FAIL"`, or `"IN REVIEW"` (uppercase, exact strings).

2. **`data`** — The error payload:
   - On PASS or when there's nothing to report: `null`
   - On FAIL or IN REVIEW: a **list** of error dicts, even if there's only one error
   - Never a bare string, dict, or other type

3. **`job_info`** — Reserved key for gear run metadata (config, inputs, job_id, version). Skipped by pipeline-event-logger during QC result iteration.

4. **Check names** — Use lowercase with hyphens or underscores. Each check name becomes the key under `file.info.qc.<gear_name>`.

## Error Dict Format (FileError Convention)

Error dicts should serialize using the `FileError` model with `by_alias=True`, producing:

```json
{
  "type": "error" | "warning" | "alert",
  "code": "<error-code>",
  "message": "<human-readable description>",
  "value": "<offending value, optional>",
  "timestamp": "<ISO timestamp, optional>",
  "location": { ... optional ... },
  "ptid": "<optional>",
  "visitnum": "<optional>",
  "date": "<optional>",
  "naccid": "<optional>"
}
```

Only `type`, `code`, and `message` are required for pipeline-event-logger extraction. The remaining fields provide context for QC status logs and downstream reporting.

### Standard Implementation

```python
from nacc_common.error_models import FileErrorList

# Write QC result
context.metadata.add_qc_result(
    file_input,
    name="validation",
    state="PASS" if success else "FAIL",
    data=(errors.model_dump(by_alias=True) if errors else None),
)
```

Where `errors` is a `FileErrorList` (Pydantic `RootModel[List[FileError]]`).

## Pipeline-Event-Logger Error Config

For NACC gears following this convention, the error_configs entry is always:

```json
{
  "check_name": "<check_name>",
  "field_mapping": {
    "type": "list",
    "message": "message",
    "error_type": "type",
    "error_code": "code"
  }
}
```

No `data_key` override needed (defaults to `"data"`).

## Third-Party Gears (e.g., dicom-qc)

Third-party gears don't follow these conventions. Their check results may have:
- String values in `data` (not extractable as structured errors)
- Different field names in error objects (`name` instead of `message`, etc.)
- Non-error dicts in `data` (classification blocks, metadata objects)

For these gears, pipeline-event-logger uses custom `field_mapping` entries that map the gear-specific field names to `FileError` fields. See `gear/pipeline_event_logger/data/dicom-qc-config.json` for an example.

## Existing Gears Following This Convention

| Gear | Check name | Status |
|------|-----------|--------|
| `form-qc-checker` | `validation` | Compliant |
| `image-identifier-lookup` | `validation` | Compliant |

Both use `FileErrorList.model_dump(by_alias=True)` for their `data` field.

## What Not to Do

```python
# ❌ Don't write a string as data
data="Something went wrong with slice consistency"

# ❌ Don't write a dict as data
data={"filename": "example.dcm", "trace": []}

# ❌ Don't write a bare list of strings
data=["error 1", "error 2"]

# ✅ Do write a list of FileError-shaped dicts (or null)
data=[{"type": "error", "code": "system-error", "message": "..."}]
data=None
```
