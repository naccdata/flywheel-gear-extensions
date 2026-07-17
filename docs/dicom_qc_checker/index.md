# DICOM QC Checker

Evaluates DICOM QC check results stored in a file's metadata and tags the file with an aggregate pass/fail status.

## Workflow

Upstream, the `dicom-qc` gear runs quality checks on DICOM files and writes individual check results into the file's metadata at `file.info.qc.dicom-qc`. Each check result is a dictionary entry with a `state` field (`"PASS"` or `"FAIL"`).

When invoked on the input file, the checker gear:

1. Extracts the `dicom-qc` metadata from `file.info.qc.dicom-qc`.
2. Filters out the `job_info` entry and any non-check entries (values that are not dicts or lack a `state` field).
3. Determines aggregate status: **PASS** only if every check result has `state == "PASS"`, otherwise **FAIL**.
4. Logs each failed or invalid check name at WARNING level.
5. Tags the file with the result using the `GearTags` mechanism.

If no QC metadata is present, or if metadata contains no valid check results after filtering, the gear logs a warning and exits successfully without modifying tags.

## Inputs

| Input | Base | Description |
| ----- | ---- | ----------- |
| `api-key` | api-key | The account the gear runs as; needs read/write permission on file metadata and tags. |
| `input_file` | file | The file to evaluate for DICOM QC check results. |

## Configuration

Gear configs are defined in [manifest.json](../../gear/dicom_qc_checker/src/docker/manifest.json).

This gear has no additional configuration parameters beyond the standard inputs.

## Status Determination

| Condition | Overall Status | Behavior |
|-----------|---------------|----------|
| All check results have state "PASS" | PASS | Tag applied |
| Any check result has state != "PASS" | FAIL | Failed checks logged, tag applied |
| No QC metadata present | N/A | Warning logged, no tag change |
| Metadata has only `job_info` (no check results) | N/A | Warning logged, no tag change |

## File Metadata and Tagging

After processing, the gear updates the input file's tags using the `GearTags` mechanism. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

- Adds `dicom-qc-checker-PASS` or `dicom-qc-checker-FAIL` based on the aggregate QC outcome
- Previous status tags for this gear are removed before adding the new one

## Expected Metadata Structure

The gear expects metadata at `file.info.qc.dicom-qc` with this shape:

```json
{
    "job_info": {
        "job_id": "abc123",
        "gear_name": "dicom-qc"
    },
    "slice_count_check": {
        "state": "PASS"
    },
    "orientation_check": {
        "state": "FAIL"
    }
}
```

Rules for identifying check results:
- Key is not `"job_info"`
- Value is a dict containing a `"state"` field

All other entries are silently ignored.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| QC metadata absent or empty | Log warning, exit code 0 (nothing to check) |
| Metadata contains only `job_info` | Log warning, exit code 0 |
| File retrieval fails (API error) | Exit code 1 |
