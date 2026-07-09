# PHI Coordinator

Finalizes the PHI review of images by reading completed reader-task form responses and applying the corresponding tags to the reviewed file.

## Workflow

An upstream `image-pii-detector` gear scans a DICOM image for burned-in PHI, tags the acquisition file `PHI-Found`, and a gear rule creates a **reader task** so a person reviews the flagged region and answers the form (*"Does the bounding box show PHI?"*, `yes`/`no`). Answering `yes` reveals a warning that the image will be deleted and a required acknowledgment checkbox (*"I understand"*) the reviewer must check to submit. When the reviewer submits, the task becomes `Complete`.

PHI Coordinator runs **on a schedule from an administrative group** (no input file). On each run it finds the completed PHI reader tasks across all accessible projects and finalizes each one's tags so downstream automation (triggered by those tags, outside this gear) can proceed.

## Inputs

This gear takes **no input file**. It requires an `api-key` input (the account it runs as), which must have read/write permission on reader tasks and form responses in the projects it processes.

## Configuration

Gear configs are defined in [manifest.json](../../gear/phi_coordinator/src/docker/manifest.json).

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `dry_run` | `false` | Log intended changes without applying them. |
| `phi_protocol_label` | `default_image_pii_detector_protocol` | Label of the reader-task protocols whose completed tasks to process. |
| `answer_key` | `phi_radio` | Key in the form `response_data` holding the yes/no answer. |
| `ack_key` | `delete_ack` | Key in the form `response_data` for the deletion-acknowledgment checkbox that must be checked before a `yes` answer is confirmed; empty disables the requirement. |
| `found_tag` | `PHI-Found` | Tag marking a file with detected PHI awaiting review; removed once resolved. |
| `confirmed_tag` | `PHI-Confirmed` | Tag added when the reviewer confirms PHI is present. |
| `not_found_tag` | `PHI-Not-Found` | Tag added when the reviewer reports no PHI. |
| `coordinated_tag` | `phi-coordinator` | Marker tag added to a reader task once processed, excluding it from future runs. |
| `reset_on_missing_data` | `true` | If a completed task has no usable answer, reset it to `Todo` and clear its response. |

## Behavior

For each completed PHI reader task that is not yet marked `coordinated_tag`:

- Read the latest form response's `answer_key`.
- **`yes`** → add `confirmed_tag` to the file; **`no`** → add `not_found_tag`.
- A **`yes`** answer is only confirmed when the `ack_key` acknowledgment checkbox is checked. A `yes` with the acknowledgment unchecked (or missing) is treated like missing data — the file is **not** tagged `confirmed_tag`. The acknowledgment is not required for a `no` answer.
- Remove `found_tag` from the file if present, and remove the opposite resolution tag if present, so the file ends with exactly one resolution tag.
- **Only after** the file tags are updated, add `coordinated_tag` to the task so it is excluded from future runs (a failed run leaves the task unmarked and it is retried).
- If a completed task has no usable answer — or confirms PHI without the acknowledgment — and `reset_on_missing_data` is set, reset the task to `Todo` and clear its response so the reviewer redoes it (the task is not marked).

Tasks are discovered with a single server-side query per protocol
(`status=Complete,protocol_id=<id>,tags!=<coordinated_tag>`), so the work set only ever contains unprocessed tasks.

## Outputs

This gear produces no output file. It updates **tags on the reviewed acquisition file** and adds a marker tag to processed reader tasks.
