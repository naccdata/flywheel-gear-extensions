# LONI Receipt Metadata

Records the outcome of a `loni-upload` run on the acquisitions whose files were uploaded to LONI. For each successfully uploaded file, the gear stores the LONI UIDs, upload dates, and status as acquisition custom info, and attaches a copy of the relevant receipt rows to the acquisition.

## Input

| Input | Base | Description |
| ----- | ---- | ----------- |
| `api-key` | api-key | The account the gear runs as; needs permission to read and write acquisitions and to tag the input file. |
| `input_file` | file | One receipt CSV, `upload_data_<timestamp>.csv`, written by the `loni-upload` gear. |

The receipt must have the columns `Upload ID`, `Directory`, and `Status`. Rows also use `LONI UID` and `Upload Date`. If the required columns are missing or the file cannot be read, the gear fails before writing anything.

## Configuration

Gear configs are defined in [manifest.json](../../gear/loni_receipt_metadata/src/docker/manifest.json).

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `dry_run` | `false` | Log what would be written without writing. Flywheel is still read to resolve file IDs. |

## How rows are matched

Each row is matched to a Flywheel file by the file ID at the start of the basename of its `Directory` value. The basename must be a 24-character lowercase hexadecimal file ID followed by `_`, that is, `<file_id>_<name>`. Rows with the same file ID form one upload. Each file ID is resolved to the acquisition that currently contains the file.

A row is successful when it has an `Upload ID`, a `Status` of `ARCHIVED`, a `LONI UID`, and an `Upload Date`. Status is compared case-sensitively after whitespace is stripped.

## What it writes

For each acquisition that has at least one successful upload:

- **Custom info.** `acquisition.info.upload_loni.<file_id>` for each successful upload:

    | Field | Value |
    | ----- | ----- |
    | `file_name` | Name of the file with that ID. |
    | `upload_id` | `Upload ID` from the receipt (the first row's, if rows differ). |
    | `status` | `Status` from the receipt (the first row's, if rows differ). |
    | `uploads` | List of `{loni_uid, upload_date}`, one per receipt row for the file. |

  Entries for other file IDs under `upload_loni` are left unchanged.

- **Receipt copy.** A CSV with the original receipt name, containing the receipt header and the rows for the files in that acquisition. It is uploaded under its original name. If the acquisition already has a file with that name, the upload creates a new version of that file.

The input receipt is tagged `loni-receipt-metadata-PASS` if every row succeeded and `loni-receipt-metadata-FAIL` otherwise. Any earlier status tag from this gear is removed.

With `dry_run`, the gear logs the entries, the receipt copy, and the tag instead of writing them.

## Failure behavior

- A row fails if its file ID cannot be read from `Directory`, the file cannot be resolved to an acquisition, its status is not successful, or it lacks a `LONI UID` or `Upload Date`.
- If any row for a file fails, nothing is written for that file: no entry and no receipt rows.
- Other files and acquisitions are still processed. After all rows are processed, the receipt is tagged and, if any row failed, the gear fails.
- If writing to an acquisition fails, all rows for that acquisition count as failed. Entries already written to it are not removed.
- Entries under `upload_loni` are never retracted or marked stale by this gear.

## Rerun behavior

Rerunning the same receipt replaces the entries for the same file IDs and uploads the receipt copy again under the same name (a new file version), and resets the tag to the current outcome. Entry writes are replacements, so a rerun after a partial failure converges.

If a file that succeeded earlier fails on a later run (for example, because it was deleted), its existing `upload_loni` entry stays. The receipt copy is rebuilt from the current run only, so that file's rows are absent from the new copy.

## Known limits

- Rows are matched by the file ID at the start of the `Directory` basename, so only upload directories named `<file_id>_<name>` resolve. Other names fail the row.
- A trailing separator in `Directory` leaves an empty basename, so the row fails.
- `Status` values other than `ARCHIVED` are treated as unsuccessful.
