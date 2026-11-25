# Requirements Document

## Introduction

After the LONI upload gear (source in `fw-loni-export`, gear name `loni-upload`) uploads the files of a session, it writes one or more receipt CSV files (`upload_data_<timestamp>.csv`) to its output. This feature adds a new, independent gear that takes one receipt as input and records, on each acquisition whose file was uploaded, the LONI UIDs and related values from the receipt, so that each acquisition can be traced to its images in LONI. The gear also attaches a copy of the receipt, limited to that acquisition's rows, to the acquisition.

Source: Card 1819, "Record the upload LONI UID in Flywheel metadata after LONI upload" (Tech Team Sprint Board), requested by Sarah George. Starting the gear with a gear rule is out of scope for this spec; the gear is given one receipt file as input.

## Glossary

- **Receipt**: A CSV file written by the `loni-upload` gear's uploader step. One row per LONI UID returned for an uploaded file.
- **Receipt_Row**: A single row of a Receipt.
- **Upload**: The set of Receipt_Rows that share the same file ID in the `Directory` column. An Upload is one uploaded Flywheel file that was split into partitions, each with its own LONI UID.
- **Directory_File_ID**: The leading 24-character file ID in a Receipt_Row's `Directory` value. The `loni-upload` gear names each directory `<file_id>_<file name stem>`, where the file ID is the Flywheel file ID of the acquisition file that was uploaded.
- **Successful_Row**: A Receipt_Row with a non-blank `Upload ID` and a `Status` in the set of success statuses used by `loni-upload` (`LONI_PROGRESS_SUCCESS_STATUS`, currently `ARCHIVED`).
- **Failed_Row**: A Receipt_Row that is not a Successful_Row, or that lacks a `LONI UID` or `Upload Date` value (including when the column is absent).
- **Upload_LONI_Entry**: The value stored at `acquisition.info.upload_loni.<file_id>`.
- **Receipt_Copy**: A CSV containing the Receipt header and only the Receipt_Rows for the files of one acquisition.
- **Input_Receipt**: The receipt file given to the gear as `input_file`.

## Requirements

### Requirement 1: Input Validation

**User Story:** As a pipeline operator, I want the gear to reject files that are not receipts, so that a wrong file does not produce metadata.

#### Acceptance Criteria

1. THE gear SHALL take one file input, `input_file`, which is the Input_Receipt.
2. IF the Input_Receipt does not contain the columns `Upload ID`, `Directory`, and `Status`, THEN THE gear SHALL fail with an error that names the missing columns.

### Requirement 2: Resolve Rows to Acquisitions

**User Story:** As a data manager, I want each uploaded file matched to its acquisition, so that metadata lands on the right container.

#### Acceptance Criteria

1. THE gear SHALL extract the Directory_File_ID from each Receipt_Row and form Uploads from rows that share a Directory_File_ID.
2. THE gear SHALL resolve each Directory_File_ID to the acquisition that contains the file with that ID.
3. A single Input_Receipt MAY resolve to more than one acquisition; THE gear SHALL process each acquisition independently.
4. IF a Directory_File_ID does not resolve to a file in an acquisition, THEN THE gear SHALL treat the rows of that Upload as Failed_Rows.

### Requirement 3: Upload Metadata on the Acquisition

**User Story:** As a data manager, I want the LONI UIDs, upload dates, and status recorded on the acquisition, so that I can trace the acquisition to its images in LONI.

#### Acceptance Criteria

1. FOR each Upload whose rows are all Successful_Rows, THE gear SHALL write an Upload_LONI_Entry to `acquisition.info.upload_loni.<file_id>` on the resolved acquisition, where `<file_id>` is the Directory_File_ID.
2. THE Upload_LONI_Entry SHALL contain `file_name` (the name of the Flywheel file with that ID), `upload_id` (the Receipt `Upload ID`), `status` (the Receipt `Status`), and `uploads`.
3. `uploads` SHALL be a list with one item per Receipt_Row of the Upload, each item containing `loni_uid` (the Receipt `LONI UID`) and `upload_date` (the Receipt `Upload Date`).
4. THE gear SHALL record every `loni_uid` of the Upload and SHALL NOT mark any of them as distinguished from the others.
5. WHEN an Upload_LONI_Entry already exists for the same `<file_id>`, THE gear SHALL replace it.
6. THE gear SHALL NOT modify Upload_LONI_Entry values for other file IDs on the same acquisition.
7. THE gear SHALL NOT write an Upload_LONI_Entry for an Upload that has any Failed_Row.

### Requirement 4: Receipt Copy on the Acquisition

**User Story:** As a data manager, I want the receipt rows for an acquisition attached to it, so that the LONI response is available with the acquisition.

#### Acceptance Criteria

1. FOR each acquisition that received at least one Upload_LONI_Entry, THE gear SHALL attach a Receipt_Copy to the acquisition.
2. THE Receipt_Copy SHALL have the same header as the Input_Receipt and SHALL contain every Receipt_Row, including Failed_Rows, whose Directory_File_ID belongs to a file of that acquisition.
3. THE Receipt_Copy SHALL have the same file name as the Input_Receipt.
4. WHEN a file with that name already exists on the acquisition, THE existing file SHALL gain a new version with the copy's content.
5. THE gear SHALL NOT attach a Receipt_Copy to an acquisition that received no Upload_LONI_Entry.

### Requirement 5: Failure Handling

**User Story:** As a pipeline operator, I want the job to fail when any row failed, so that failures are visible in Flywheel.

#### Acceptance Criteria

1. THE gear SHALL process every Upload in the Input_Receipt before reporting failure.
2. FOR each Failed_Row, THE gear SHALL log a warning that includes the Directory_File_ID and the row's `Status`.
3. IF the Input_Receipt contains any Failed_Row, THEN THE gear SHALL complete with a non-zero failure after processing all Uploads.

### Requirement 6: Mark the Input Receipt

**User Story:** As a pipeline operator, I want the receipt tagged with the outcome, so that I can see in Flywheel which receipts were handled.

#### Acceptance Criteria

1. WHEN the gear completes with no Failed_Row, THE gear SHALL add the tag `<gear-name>-PASS` to the Input_Receipt, using `GearTags`.
2. WHEN the gear completes with any Failed_Row, THE gear SHALL add the tag `<gear-name>-FAIL` to the Input_Receipt, using `GearTags`.

### Requirement 7: Dry Run

**User Story:** As a developer, I want a dry-run option, so that I can check a receipt without changing Flywheel.

#### Acceptance Criteria

1. THE gear SHALL provide a `dry_run` configuration option, default false.
2. WHILE `dry_run` is true, THE gear SHALL log the metadata, Receipt_Copies, and tag it would write, and SHALL NOT write any of them.

### Requirement 8: Gear Conventions

**User Story:** As a maintainer, I want the gear to follow repository conventions, so that it builds, tests, and is maintained like the other gears.

#### Acceptance Criteria

1. THE gear SHALL be an independent gear under `gear/` with `run.py` for gear interface and Flywheel context handling and `main.py` for logic that does not depend on the gear context.
2. THE gear SHALL authenticate with the caller's key (`ContextClient`) and SHALL NOT require the parameter store.
3. THE gear's top-level package names SHALL be added to `known-first-party` in `ruff.toml`.
4. THE gear's tests SHALL be in a `{app_name}_test` package that contains an `__init__.py`.

## Decisions Recorded From Discussion

- A receipt's UIDs are all for the undefaced image. The defaced UID is returned by LONI later and is out of scope.
- A set of rows sharing a file ID is one uploaded file split into partitions, each with its own LONI UID.
- `acquisition.info` is keyed by file ID, not by file name, because file names contain dots and one acquisition may hold more than one file.
- Nothing is written for failed rows; the job fails after all rows are processed.
- Test mocks: extend the shared mocks in `common/src/python/test_mocks/mock_flywheel.py` (add `get_file`/`get_acquisition` to `MockFlywheelProxy`, and `info`, `update_info`, `upload_file` to `MockAcquisition`) instead of building gear-local `Mock(spec=...)` fixtures. The design names the extension as required work and keeps existing tests passing.
- Write order per acquisition: write the `upload_loni` entries first, then attach the Receipt_Copy. If attaching the copy fails after the entries were written, the entries stay (a rerun replaces them with identical content), the rows of that acquisition count as failed, the job fails and the Input_Receipt is tagged `-FAIL`. Requirement 3.7 therefore applies to row-level failures only. A test covers this case.
- Reuse: `flywheel_io.py` keeps only the protocol implementations with no repo equivalent (file resolver, acquisition target, receipt tagger, and their dry-run versions). One generic piece is added as new, additive code with no change to existing callers: a method on `GearTags` in `nacc-common` that returns the tags to add and remove for a status. Existing gears (`phi_image_removal`, the four gears with their own PASS/FAIL tag swap, `SubjectAdaptor`) are NOT refactored in this task. Refactoring them to use the shared code is a follow-up after this gear exists.
- Permissions: assume the gear runs with sufficient permission to tag the Input_Receipt. This is a stated assumption, not a probed result; the design records it as an assumption and needs no probe.
- Flywheel versions files: uploading a file with an existing name to an acquisition creates a new version of that file (settled by the user). Requirement 4.4 relies on this, and no delete or conflict handling is needed.

## Open Items

- Gear name and the `<gear-name>` used in tags are not decided.
- Whether `Upload ID` is the LONI study ID is unknown. The spec stores it as `upload_id` and treats it as a pass-through value. To confirm with Sarah George.
- Whether the caller's key can write tags on the analysis file that holds the Input_Receipt is unchecked.
- Whether Flywheel rejects dots in `info` keys is unverified. The design uses file IDs, which have none.
- Other gears' use of `acquisition.info` has not been checked for a collision with the key `upload_loni`.
- The `Upload Date` values are strings such as `2026-09-21 09:14:51`. Whether to store them as written or in another format is not decided.
