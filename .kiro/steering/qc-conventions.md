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

## Error Handling: `-FAIL` tag / QC `FAIL` vs. `GearExecutionError`

Gears must distinguish a **per-item data problem** from a **whole-gear failure**,
because the two mean different things to the pipeline and to the Flywheel job
state.

### The convention

- **Per-item data problem** — a record, file, subject, or session whose data is
  bad or unresolvable (e.g. no unique `record_id` can be determined, conflicting
  information between sources, unexpected or missing field values). Record the
  failure as a signal and let the gear **exit normally (exit 0)**:
  - write a QC result with `state="FAIL"` (see the QC Result Structure above), and/or
  - apply the `<gear_name>-FAIL` tag.

  This says "the gear ran as expected; this item's data is in a failed state."
  The gear should stop processing that item and move on (or return), not raise.

- **Whole-gear / precondition / infrastructure failure** — the gear cannot run
  as intended (e.g. a required input file is missing, config can't be parsed,
  the destination container isn't the expected type, an external service or API
  call fails, a required project/metadata value is absent). Raise
  `GearExecutionError`.

  The shared engine in `common/src/python/gear_execution/gear_execution.py`
  catches `GearExecutionError` and calls `sys.exit(1)`, which fails the Flywheel
  **job**. A failed job should mean "the gear could not run," not "the gear ran
  and found the data bad."

### Why

Downstream gears (`form-scheduler`, `form-qc-coordinator`,
`pipeline-event-logger`) key off the `-PASS`/`-FAIL` tag and the QC `state`,
read via Flywheel search filters — **not** off the producing job's exit code. A
gear that tags `-FAIL` and exits 0 is fully visible to the pipeline and the
Flywheel UI. Raising additionally marks the job failed, which is misleading
noise when the data condition was expected and already captured by the tag/QC
state. Failed sessions are discoverable from the `-FAIL` tag; a failed job is
not required to surface them.

### Reference implementations

- `form_qc_checker` — writes `validation` QC `PASS`/`FAIL` + tag, exits 0 on bad
  data; raises `GearExecutionError` only for setup problems (missing input,
  unreadable config, inaccessible S3).
- `identifier_lookup` — unexpected values / unresolvable IDs write an error and
  return `False` (no raise); raises only when the identifier *service* errors.
- `image_identifier_lookup` — data lookup failures set `success = False`
  (no raise); missing project metadata / PTID raise `GearExecutionError`.

### What not to do

```python
# ❌ Don't tag -FAIL AND raise for an ordinary data condition
def tag_fail(session, msg) -> NoReturn:
    session.add_tag(f"{gear_name}-FAIL")
    raise GearExecutionError(msg)   # fails the job for a data problem

# ✅ Do tag / record QC FAIL and return for a data condition
def tag_fail(session, msg) -> None:
    session.add_tag(f"{gear_name}-FAIL")
    log.warning(msg)
    # caller stops processing this item and continues / returns

# ✅ Do raise only for genuine preconditions / infrastructure
if destination_type != "session":
    raise GearExecutionError(f"Expected a session, given {destination_type}")
```

Prefer the shared `nacc_common.error_models.GearTags` helper for tag management
(it manipulates tags only and never raises) and `add_qc_result(..., state=...)`
for the QC state, so every gear emits the same signals the pipeline reads.
