# REDCap Image Form Creator

Creates a new record in the REDCap Image Submission EDC project by collecting imaging metadata from a Flywheel session.

## Workflow

When triggered on a session (or an acquisition within a session), the gear:

1. Collects session-level metadata (ADCID, NACCID, PTID, data access group, timestamps).
2. Inspects each acquisition's DICOM headers for scan date, modality, uploader, and PET-specific tags.
3. Generates a unique `record_id` for the session based on existing records in the REDCap project.
4. Imports the new record into REDCap via the API.
5. Stores the assigned `record_id` in the session's custom info on Flywheel.
6. Tags the session with `redcap-image-form-creator-PASS` or `redcap-image-form-creator-FAIL`.

If required fields are missing from the Flywheel data, the gear fails with a descriptive error and tags the session as failed.

## Inputs

| Input | Base | Description |
| ----- | ---- | ----------- |
| `api-key` | api-key | Flywheel API key with read/write access to sessions and acquisitions. |

## Configuration

Gear configs are defined in [manifest.json](../../gear/redcap_image_form_creator/src/docker/manifest.json).

| Parameter | Type | Default | Description |
| --------- | ---- | ------- | ----------- |
| `dry_run` | boolean | `false` | Collect data without modifying REDCap or Flywheel. |
| `parameter_path` | string | `/redcap/aws/image-submission-edc` | AWS SSM parameter path for REDCap API credentials. |

## REDCap Project

The gear writes to the **Image Submission EDC** REDCap project. Connection credentials are read from AWS SSM Parameter Store at the configured `parameter_path`.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Missing required imaging metadata | Gear fails, session tagged FAIL |
| Unable to generate unique record_id | Gear fails, session tagged FAIL |
| Dry run mode | Data collected and logged, no modifications made |
