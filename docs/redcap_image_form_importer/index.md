# REDCap Image Form Importer

Imports image form data from the REDCap Image Submission EDC project back into Flywheel, verifying consistency between the two systems.

## Workflow

When triggered on a session (or an acquisition within a session), the gear:

1. Retrieves the session's `record_id` from Flywheel custom info.
2. Exports the corresponding record from the REDCap Image Submission EDC project.
3. Verifies that Flywheel session metadata matches the REDCap record for all required fields.
4. Checks that REDCap indicates the record is permitted for import.
5. Collects the relevant REDCap variables (varying by modality: MRI or PET).
6. Writes the collected form data as a JSON file to the gear output directory.
7. Tags the session with `redcap-image-form-importer-PASS` or `redcap-image-form-importer-FAIL`.

## Inputs

| Input | Base | Description |
| ----- | ---- | ----------- |
| `api-key` | api-key | Flywheel API key with read/write access to sessions. |

## Configuration

Gear configs are defined in [manifest.json](../../gear/redcap_image_form_importer/src/docker/manifest.json).

| Parameter | Type | Default | Description |
| --------- | ---- | ------- | ----------- |
| `dry_run` | boolean | `false` | Collect data without modifying Flywheel tags or writing output. |
| `parameter_path` | string | `/redcap/aws/image-submission-edc` | AWS SSM parameter path for REDCap API credentials. |

## REDCap Project

The gear reads from the **Image Submission EDC** REDCap project. Connection credentials are read from AWS SSM Parameter Store at the configured `parameter_path`.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Session missing `record_id` in custom info | Gear fails, session tagged FAIL |
| Flywheel metadata doesn't match REDCap record | Gear fails, session tagged FAIL |
| REDCap record not permitted for import | Gear fails, session tagged FAIL |
| Dry run mode | Data collected and logged, no modifications made |
