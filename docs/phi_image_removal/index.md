# PHI Image Removal

Removes an image file that has been confirmed to contain PHI, leaving a JSON **tombstone** in its place that records the deleted file's details.

## Workflow

Upstream, the `image-pii-detector` gear flags a DICOM image with `PHI-Found`, a reviewer answers the PHI form, and the `phi-coordinator` gear finalizes the review by tagging the file `PHI-Confirmed` (PHI is present) or `PHI-Not-Found`.

PHI Image Removal is triggered by a **gear rule** that matches the confirmed image file and passes it as the `input_file`. For that file the gear:

1. Verifies the file carries the `confirmed_tag` (`PHI-Confirmed`). If not, it does nothing.
2. Captures the file's details into a tombstone record.
3. Uploads the tombstone JSON (the original base name with a `.json` extension) into the same acquisition.
4. Tags the tombstone file `tombstone_tag` (`PHI-Tombstone`).
5. Deletes the original image file.

The actions are ordered so the original image is **never deleted without a tagged tombstone already in place**: upload the tombstone, tag it, then delete the image.

## Inputs

| Input | Base | Description |
| ----- | ---- | ----------- |
| `api-key` | api-key | The account the gear runs as; needs read/write/delete permission on files in the acquisition. |
| `input_file` | file | The image file (the parent acquisition is resolved from `file.parents.acquisition`). |

## Configuration

Gear configs are defined in [manifest.json](../../gear/phi_image_removal/src/docker/manifest.json).

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `dry_run` | `false` | Log intended changes without applying them. |
| `confirmed_tag` | `PHI-Confirmed` | Tag marking a file as confirmed to contain PHI; required for removal. |
| `tombstone_tag` | `PHI-Tombstone` | Tag added to the JSON tombstone left in place of the removed image. |

## Tombstone contents

The tombstone JSON has two sections:

- `tombstone` — provenance of the removal: `removed_by_gear`, `gear_version`, `removed_at` (UTC ISO timestamp), and `reason` (the confirming tag).
- `original_file` — best-effort details of the deleted file: `name`, `file_id`, `size`, `type`, `mimetype`, `modality`, `classification`, `tags`, `hash`, `version`, `created`, `modified`, `origin`, `info`, and the container `parents` hierarchy.

## Behavior

- If the input file does not have `confirmed_tag`, the gear logs and exits without changes (no-op).
- If a tombstone of the target name already exists in the acquisition, the gear logs and skips (no re-upload, no deletion).
- If the tombstone cannot be found after upload, the gear fails and leaves the original file in place.
- All actions are `dry_run`-aware.

## Outputs

This gear produces a **JSON tombstone file** in the acquisition (tagged `tombstone_tag`) and **deletes** the confirmed-PHI image file.
