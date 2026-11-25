# Design Document: LONI Upload Receipt Metadata

## Overview

A new independent gear, `loni-receipt-metadata`, takes one receipt CSV written by the `loni-upload` gear (`upload_data_<timestamp>.csv`) as `input_file`. It groups the receipt rows into Uploads by the file ID at the start of the `Directory` value, resolves each file ID to its acquisition, and records the LONI UIDs, upload dates and status at `acquisition.info.upload_loni.<file_id>`. For each acquisition that received at least one entry, it attaches a copy of the receipt limited to that acquisition's rows. The gear processes every row, tags the input receipt `loni-receipt-metadata-PASS` or `-FAIL`, and then fails the job if any row failed.

The requirements in `requirements.md` are authoritative. Terms (Upload, Directory_File_ID, Successful_Row, Failed_Row, Upload_LONI_Entry, Receipt_Copy, Input_Receipt) are used as defined there.

**Technology stack (locked on approval):** Python 3.12, Pants monorepo, `fw_gear.GearContext`, `flywheel-sdk`, the repo's `gear_execution` (`GearEngine`, `ContextClient`, `InputFileWrapper`, `GearExecutionEnvironment`), `flywheel_adaptor.flywheel_proxy.FlywheelProxy`, `nacc_common.error_models.GearTags`, standard-library `csv`, `pytest`. No new third-party dependency. No pydantic model is needed; the receipt is flat string data, and frozen dataclasses are enough.

## Resolution of Open Items

| Item | Resolution | Evidence |
|---|---|---|
| (a) Gear name and tag prefix | Gear name `loni-receipt-metadata`. Tags are `loni-receipt-metadata-PASS` and `loni-receipt-metadata-FAIL`. Directory `gear/loni_receipt_metadata`, app package `loni_receipt_metadata_app`, test package `loni_receipt_metadata_test`. | Repo gears use kebab-case manifest names with snake_case directories and `_app` packages (`pipeline-event-logger` / `pipeline_event_logger` / `pipeline_event_logger_app`). The name must differ from `loni-upload`: that gear's README documents `loni-upload-PASS/-FAIL/-SKIP` tags on sessions and files, and a shared prefix would make a receipt tag look like an upload outcome. `loni-receipt-metadata-PASS` does not equal any of them. |
| (b) Dots in `info` keys | Not verified server-side. The SDK warns client-side and its message says `.` becomes `_` (the server sanitizes). Nothing in the repo shows the server rejecting such keys. The design avoids the question: keys are file IDs (24 hex characters), so no key contains a dot. | `flywheel/models/mixins.py` `_warn_if_keys_will_be_sanitized` (client-side warning only). This is why keys are IDs rather than file names. |
| (c) Collision on `acquisition.info.upload_loni` | None found within the searched scope: this repo (`gear/`, `common/`, `nacc-common/`, `scripts/`) and `fw-loni-export`. The design review also searched `nacc-attribute-deriver`, `nacc-flywheel-metadata` and `clariti-advanced-mri` and found no `upload_loni`. Writers in any other repository are not known. No gear in this repo writes `upload_loni`, and no gear here writes acquisition-level `info` at all (searched `gear/` and `common/src`). `loni-upload` writes only session/file tags and QC, and its own session metadata, not acquisition info. | Repo-wide grep for `upload_loni` and `upload-loni` finds only this spec. Grep of `fw-loni-export/fw_gear_loni_upload` for `update_info`/`replace_info`/`acquisition.info` finds only a comment about `session.info`. |
| (d) Can the caller's key tag the analysis file holding the receipt? | **Assumed yes; not probed.** Per the decisions in `requirements.md`, the gear is assumed to run with permission to tag the Input_Receipt. No probe gates the design. The repo cannot prove server-side permission either way. Existing `ContextClient` gears tag their input only through `context.metadata.add_file_tags` (`identifier_provisioning`, `legacy_sanity_check`, `gather_submission_status`), which Flywheel applies after a clean exit. That path is unusable here: `GearContext.__exit__` writes `.metadata.json` only on a clean exit, and a FAIL run exits 1, so the FAIL tag would be lost exactly when needed. The gear therefore tags with the SDK file-ID endpoints `client.add_file_tags(file_id, body=[...])` and `client.delete_file_tags(file_id, body=[...])` (the calls `loni-upload` uses in `file_instance.py`), with the caller's key, where `client` is `ClientWrapper.client`. If the first real run (check M2) shows the tag call refused, the failure surfaces as `GearExecutionError` (see Error Handling) and the issue returns to the requirements owner, because Requirement 8.2 excludes a gear-bot or parameter-store fallback. The tagger's read-failure rule is specified once under `FlywheelReceiptTagger` (it is a per-call try/except on the tag read, because whether `client.get_file` accepts analysis file IDs is unverified). | `fw_gear/context.py` `__exit__`; comment on `_tag_output_file` in `gear/center_form_export/.../run.py`; `reset_visit_qc_metadata` in `common/src/python/uploads/acquisition.py` tags `FileEntry` objects directly for the same reason. |
| (e) Look up acquisition and file name from a file ID | `FlywheelProxy.get_file(file_id)` returns the `FileEntry` (gives `name` and `parents.acquisition`); `FlywheelProxy.get_acquisition(acquisition_id)` returns the acquisition. A file whose `parents.acquisition` is empty (project, subject, session or analysis file) is treated as not resolving to an acquisition. The resolver also confirms the file is currently in the acquisition (`acquisition.reload().files` contains a file whose `file_id` equals the ID), which handles deleted files (see Edge Cases). | `common/src/python/flywheel_adaptor/flywheel_proxy.py` lines 220 and 682; `gear/phi_image_removal/.../run.py` uses `file.parents.acquisition` the same way. |
| (f) Upload Date format | Stored as written, a string such as `2026-09-21 09:14:51`. No parsing, no timezone assumption. Reason: the receipt does not state a timezone, so any reformatting would invent one; and it keeps `uploads` identical to the receipt rows. | Sample receipt values; requirement 3.3 says "the Receipt `Upload Date`". |
| Open item: `Upload ID` meaning | Unchanged: stored as `upload_id`, pass-through. To confirm with Sarah George; no code depends on the answer. | requirements.md |

## Key Decisions

**Gear shape.** Follows `gear/pipeline_event_logger` (`ContextClient`, `GearEngine().run`, `dry_run` option) and the repo split in `AGENTS.md`: `run.py` holds the gear context, the file input and the Flywheel-bound objects. `main.py` and `receipt.py` hold logic that never imports `fw_gear`. The visitor's `create` ignores its `parameter_store` argument (the `pipeline_event_logger` precedent). The gear category is `utility`, with no output files, so no `.metadata.json` is needed.

**Dry run by injection, not by flag.** Per the repo's dependency-injection guideline, `main.py` has no `dry_run` boolean. `run.py` chooses between a real and a dry implementation of two small interfaces: `AcquisitionTarget` (writes to one acquisition) and `ReceiptTagger` (tags the input receipt). The dry implementations log what they would write and perform no write. Reads (resolving file IDs) still happen in a dry run so that the log shows real resolution results. `ContextClient.create` also passes `dry_run` to the `ClientWrapper`, and `ClientWrapper.get_proxy` passes it to `FlywheelProxy`. This is harmless: `FlywheelProxy.get_file` and `get_acquisition` (`flywheel_proxy.py`, `return self.__fw.get_file(...)` / `get_acquisition(...)`) do not check `dry_run`, so reads are real in a dry run, and the gear's writes go through the injected objects, not the proxy, so the proxy's dry-run guards on write methods are never reached.

**Where `upload_loni` data is merged.** The real `AcquisitionTarget` does a read-merge-write of the whole `upload_loni` object: `current = self.__acquisition.reload()` (the SDK `reload()` returns a new object and does not refresh the original in place, so always read `current.info`, never the stale `self.__acquisition.info`), `existing = dict(current.info.get("upload_loni", {}))`, assign the new entries by file ID (replacing any existing entry for the same ID, leaving other IDs alone), then call `self.__acquisition.update_info({"upload_loni": existing})`. Reason: the `loni-upload` source documents that `update_info` replaces the whole second-level subdict rather than merging into it, so sending only the new entries would delete entries for other files. Sending the merged object is correct whether the server merges or replaces. A concurrent writer between the read and the write could lose an update; there is no other writer of this key, and the gear is run once per receipt, so no locking is added.

**Alternatives considered for receipt splitting and write order.** Writing info and the copy in one pass per acquisition was chosen over a two-phase "all info, then all copies" pass, because acquisitions are independent (Requirement 2.3) and a failure in one should not prevent another from completing. Per acquisition the order is info first, then copy; both are idempotent replacements, so a re-run after a partial failure converges.

**Failure model.** Row failures (non-success status, missing UID/date, unresolved file ID) are data conditions: logged, counted, and never raise. If `write_upload_loni` or `attach_receipt_copy` raises `TargetWriteError` for an acquisition, every row of that acquisition becomes a Failed_Row for the run: one warning per row with Directory_File_ID and `Status` (Requirement 5.2), added to the failed-row count. Other acquisitions continue. If `attach_receipt_copy` fails after `write_upload_loni` succeeded, the entries stay on the acquisition (a re-run replaces them with identical content); Requirement 3.7 and the invariant "nothing written for an Upload with a failed row" apply to row-level failures only, and the invariant table is qualified accordingly. This follows the decision recorded in `requirements.md` (entries first, then copy). This keeps Requirements 5.3 and 6.1/6.2 literal: the tag is PASS exactly when there are no Failed_Rows. The job fails after all Uploads are processed and the receipt is tagged. Only a malformed receipt or an unreadable input stops the gear before any write.

## Components and Files

All paths relative to the repo root. Nothing outside this list is modified except `ruff.toml`. Besides the new gear, the task adds code to three shared modules, all additive with no change to existing callers: `common/src/python/uploads/acquisition.py`, `nacc-common/src/python/nacc_common/error_models.py` and `common/src/python/test_mocks/mock_flywheel.py`. Each is described under "Shared additions" below.

### New: `gear/loni_receipt_metadata/`

```
gear/loni_receipt_metadata/
  src/docker/{BUILD, Dockerfile, manifest.json, .gitignore}
  src/python/loni_receipt_metadata_app/{BUILD, __init__.py, run.py, main.py, receipt.py, flywheel_io.py}
  test/python/loni_receipt_metadata_test/{BUILD, __init__.py, conftest.py, test_receipt.py, test_main.py, test_flywheel_io.py, test_run.py}
  data/{.gitignore, <sanitized fixtures>}
```

Copy the Docker/BUILD layout from `gear/pipeline_event_logger/src/docker` and `.../src/python/pipeline_event_logger_app/BUILD` (`python_sources`, `pex_binary(name="bin", entry_point="run.py")`, `docker_image` with `image_tags`). Test BUILD follows `pipeline_event_logger_test/BUILD` (`python_test_utils` for `conftest.py`, `python_tests`). Run `pants tailor` for any BUILD file not copied by hand.

### `src/docker/manifest.json`

- `name`: `loni-receipt-metadata`; `label`: "LONI Receipt Metadata"; `custom.gear-builder.category`: `utility`; `image`: `naccdata/loni-receipt-metadata:<version>`; `suite`: "NACC Data Gears".
- `version`: the first release value, `0.0.1`, set identically in `manifest.json` (`version` and `custom.gear-builder.image`) and the BUILD `image_tags`. This is an initial value for a new component, not a bump of an existing one. No CHANGELOG is created or edited in this task.
- `inputs`: `api-key` (`base: api-key`), and `input_file` (`base: file`, description "Receipt CSV (`upload_data_<timestamp>.csv`) written by the loni-upload gear"). No `optional`, so `InputFileWrapper.create` raises when it is absent.
- `config`: `dry_run` (boolean, default false, "Log what would be written without writing").
- `command`: `/bin/run`.

### `receipt.py` (pure Python, no Flywheel imports)

- `REQUIRED_COLUMNS = ("Upload ID", "Directory", "Status")`.
- `SUCCESS_STATUSES = frozenset({"ARCHIVED"})`, with a comment naming `LONI_PROGRESS_SUCCESS_STATUS` in `fw-loni-export/fw_gear_loni_upload/constants.py` as the source to keep in sync. It is a module constant, not configuration (YAGNI).
- `class ReceiptError(Exception)`: malformed receipt.
- `@dataclass(frozen=True) class ReceiptRow`: `values: dict[str, str]` (raw values, unstripped, used for the copy). Properties return stripped values with `""` for an absent column: `upload_id`, `status`, `loni_uid`, `upload_date`, `directory`. `directory_file_id: Optional[str]` (the glossary's "leading 24-character file ID in the `Directory` value" refers to the leading part of the final path component: the sample receipts hold values such as `/flywheel/v0/work/tmpsb8728sm/6aac4df1634d4d3ce4b9ef01_00002-...dicom`, so the design takes the basename first; requirements.md is unchanged) is the match of `^[0-9a-f]{24}(?=_)` on `posixpath.basename(directory)` (the export gear names each directory `<file_id>_<name>`, either the downloaded file path or the extracted directory, both on Linux), else `None`. `is_successful` is `bool(upload_id) and status in SUCCESS_STATUSES`. `is_failed` is `not is_successful or not loni_uid or not upload_date`.
- `@dataclass(frozen=True) class Receipt`: `name: str`, `header: list[str]`, `rows: list[ReceiptRow]`. `to_csv(rows: Sequence[ReceiptRow]) -> str` writes the original header followed by the given rows, with `csv.writer(quoting=csv.QUOTE_ALL)` (the samples quote every field), default `\r\n` terminator, values taken from `ReceiptRow.values` in header order.
- `parse_receipt(name: str, stream: TextIO) -> Receipt`: reads with `csv.reader`.

Receipt validation rules:

| Input | Rule | On failure |
|---|---|---|
| Receipt file | Required; UTF-8 (a leading BOM is tolerated, opened with `utf-8-sig` in `run.py`); no size limit beyond memory (receipts have tens of rows) | Unreadable or undecodable file: `GearExecutionError` from `run.py`, fatal, logged at error, no writes, no tag |
| Header | Must contain `Upload ID`, `Directory`, `Status` (Requirement 1.2). Other columns optional, including `LONI UID` and `Upload Date`. An empty file counts as missing all three. Duplicate header names are tolerated (design choice; 1.2 does not require rejection): the last column wins and a warning is logged | Missing columns: `ReceiptError` naming them; `run.py` converts it to `GearExecutionError`, fatal, no writes, no tag |
| Row longer than header | Extra cells ignored (tolerant; 1.2 does not require rejection) | Warning with the row number |
| Row shorter than header | Padded with `""` | Row then fails the normal rules if a needed value is blank |
| Blank lines | Skipped | none |
| Header only, no rows | Valid; zero Uploads | Logged at warning; gear tags PASS (no Failed_Row exists) |
| `Directory` without a 24-hex file ID prefix | Row is a Failed_Row with no Directory_File_ID | Warning logged with the raw `Directory` in place of the file ID |

Whitespace is stripped from values before comparison, matching the export gear's `_is_row_successful`.

### `main.py` (no `fw_gear` import)

```python
class AcquisitionTarget(Protocol):
    @property
    def label(self) -> str: ...
    def write_upload_loni(self, entries: Mapping[str, dict[str, Any]]) -> None: ...
    def attach_receipt_copy(self, name: str, contents: str) -> None: ...

@dataclass(frozen=True)
class ResolvedFile:
    file_id: str
    file_name: str
    acquisition_id: str
    acquisition: AcquisitionTarget

class FileResolver(Protocol):
    def resolve(self, file_id: str) -> Optional[ResolvedFile]: ...

class ReceiptTagger(Protocol):
    def mark(self, passed: bool) -> None: ...

class TargetWriteError(Exception):
    """A write to an acquisition failed; raised by AcquisitionTarget implementations."""

@dataclass(frozen=True)
class ReceiptResult:
    failed_rows: int
    @property
    def passed(self) -> bool: ...   # failed_rows == 0

class ReceiptProcessor:
    def __init__(self, receipt: Receipt, resolver: FileResolver) -> None: ...
    def run(self) -> ReceiptResult: ...
```

`ReceiptProcessor.run` algorithm:

1. Group rows by `directory_file_id`, keeping receipt order. Rows with `None` go to a failed group, each logged (Requirement 5.2).
2. For each file ID, call `resolver.resolve(file_id)` once. `None` means every row of the Upload is failed (Requirement 2.4) and logged with its status.
3. For each resolved Upload, build the entry only if no row `is_failed` (Requirements 3.1, 3.7). Entry: `{"file_name": resolved.file_name, "upload_id": first.upload_id, "status": first.status, "uploads": [{"loni_uid": r.loni_uid, "upload_date": r.upload_date} for r in rows]}`, with `uploads` in receipt order and no distinguished item (Requirement 3.4). If rows of one Upload differ in `upload_id` or `status`, the first row's value is used and a warning is logged (assumption; the samples show identical values within an Upload). Every failed row of the Upload is logged at warning with file ID and `Status` (Requirement 5.2).
4. Group resolved Uploads by `acquisition_id`. For each acquisition that has at least one entry: call `write_upload_loni(entries)`, then `attach_receipt_copy(receipt.name, receipt.to_csv(rows_of_that_acquisition))`, where `rows_of_that_acquisition` are all rows (failed rows included) whose file ID resolved to that acquisition, in receipt order (Requirement 4.2). An acquisition with no entry gets neither call (Requirements 3.7, 4.5). On `TargetWriteError` from either call, log at error with acquisition label and receipt name, treat every row of that acquisition (all of its Uploads) as a Failed_Row: for each such row not already counted as failed, log a warning with Directory_File_ID and `Status` and add it to the failed-row count (rows already counted, such as failed rows of a resolved Upload, are neither logged nor counted again), and continue. `main.py` imports no `flywheel` module; it only knows `TargetWriteError`.
5. Return `ReceiptResult`. Failed rows are tracked by row identity (receipt row index), so each is counted and warned about once, whether it failed for one reason, two, or through a `TargetWriteError`.

`ReceiptProcessor` does not log or write anything about the final PASS/FAIL; `run.py` does, so the tag always goes on before the job fails.

### `flywheel_io.py` (Flywheel-bound implementations)

- `FlywheelFileResolver(proxy: FlywheelProxy, target_factory: Callable[[Acquisition], AcquisitionTarget])`. `proxy` is `ClientWrapper.get_proxy()`. Each single read (`get_file`, `get_acquisition`, `reload`) is wrapped in `api_retry` (retried 3 times, then the `ApiException` is handled as described below), the same as the writes, so one transient 5xx does not mark an Upload failed. The target's `label` is `acquisition.label` (the dry-run target takes the same value). `resolve` calls `proxy.get_file(file_id)`. An `ApiException` (404 or any other status) is logged at warning with the status and returns `None`. If `file.parents.acquisition` is empty, logs a warning ("file is not in an acquisition") and returns `None`. Otherwise it calls `proxy.get_acquisition(file.parents.acquisition)` (cached per acquisition ID so that one acquisition object and one target are shared by all its files), then calls `fresh = acquisition.reload()` once per acquisition (`reload()` returns a new object; the original is a stale snapshot) and requires some file in `fresh.files` with `file_id == file_id`. The cached object per acquisition ID is `fresh`, and `target_factory(fresh)` receives it; if none, it logs a warning ("file is not in the acquisition") and returns `None`. Otherwise it returns `ResolvedFile(file_id, file.name, fresh.id, target_factory(fresh))`. An `ApiException` on the acquisition lookup is handled like the file lookup. A transient API error therefore produces FAIL rather than a crash; re-running the receipt is safe. A 404 from `get_file` or `get_acquisition` is expected for deleted files. Decision: the extra retries are accepted. `api_retry` retries every `ApiException`, so a 404 logs three retry warnings before the resolver's own warning; no 404 special case is added, to keep one retry path.
- `FlywheelAcquisitionTarget(acquisition)`: `write_upload_loni` reloads the acquisition, merges as described under Key Decisions, and calls `update_info` (wrapped in `api_retry`). `attach_receipt_copy` builds `FileSpec(name=name, contents=contents, content_type="text/csv")` and calls the shared `replace_in_acquisition(acquisition, file_spec)` (see "Shared additions"), which owns the same-name replacement and the 409 fallback. Expected behavior, not verified in this repo: an upload with an existing name creates a new version of that file, which is the replacement in Requirement 4.4, with no window without a copy. Check M3 confirms whether the 409 path applies. The target catches the `ApiException` that escapes `replace_in_acquisition` and re-raises it as `TargetWriteError` (chained), so `main.py` never sees Flywheel exceptions.
- `DryRunAcquisitionTarget(label)`: logs at info `DRY RUN: would set upload_loni.<file_id> = <entry> on acquisition <label>` for each entry, and `DRY RUN: would attach <name> (<n> rows) to acquisition <label>` followed by the full CSV text of the Receipt_Copy (Requirement 7.2 asks for the copies to be logged; receipts have tens of rows). Because it never reads existing info, the dry run does not simulate the merge.
- `FlywheelReceiptTagger(*, client: Client, file_id: str, gear_name: str)`, where `client` is the SDK client `ClientWrapper.client`. `mark(passed)` takes `status = "PASS"` or `"FAIL"` and asks the shared `GearTags(gear_name).tag_changes(current, status)` (see "Shared additions") which tags to add and which to remove. The tagger holds only the SDK calls and error handling. One rule, applied on every call:
1. In a try block, call `client.get_file(file_id)` and set `current = list(file.tags or [])`. On `ApiException`, set `current = None` and log a warning ("cannot read tags; clearing stale tag unconditionally").
2. Call `to_add, to_remove = tag_changes(current, status)`. With a list, it returns only the changes needed (the opposite tag only if present, the new tag only if absent). With `None`, it returns the new tag to add and the opposite tag to remove, both unconditionally.
3. For each tag in `to_remove`, call `delete_file_tags(file_id, body=[tag])`; for each in `to_add`, call `add_file_tags(file_id, body=[tag])`. When `current` is `None`, an `ApiException` from the `delete_file_tags` call alone is logged at warning and ignored (the tag may simply be absent).
4. An `ApiException` from `add_file_tags`, or from `delete_file_tags` when `current` is a list, is raised as `GearExecutionError` (logged at error): the receipt would otherwise show no outcome, so the job fails.
- `DryRunReceiptTagger(gear_name)`: logs the tag that would be set.

### Shared additions (new code, no change to existing callers)

Both pieces are generic and have no LONI-specific content, so they live in shared modules and the gear's `flywheel_io.py` keeps only the five protocol implementations with no repo equivalent (`FlywheelFileResolver`, `FlywheelAcquisitionTarget`, `FlywheelReceiptTagger` and the two dry-run classes). Basis: a search of `common/`, `nacc-common/` and the other gears found no acquisition adaptor and no existing code for acquisition info merges, same-name replacement or tagging by file ID.

**`common/src/python/uploads/acquisition.py`: `replace_in_acquisition(acquisition: Acquisition, file_spec: FileSpec) -> None`**, placed beside `_upload_file`.

- Calls `_upload_file(acquisition, file_spec)` (the existing `api_retry`-wrapped single upload). If it raises `ApiException` with status 409, it calls a new private `_delete_file(acquisition, name)` (`@api_retry`, one `acquisition.delete_file(file_spec.name)` call) and then `_upload_file` again, accepting a short window without a copy. Any other status, and any failure of the delete or the second upload, propagates as the original `ApiException`. No new exception type.
- `api_retry` retries every `ApiException` immediately, including a 409, so a 409 is retried three times before the fallback runs. This is accepted.
- `upload_to_acquisition` is not changed and gets no flag. It keeps its duplicate-skip behavior, its label arguments and its extra reload, none of which the gear needs.

**`nacc-common/src/python/nacc_common/error_models.py`: `GearTags.tag_changes(self, tags: Optional[List[str]], status: str) -> Tuple[List[str], List[str]]`**, placed beside `update_tags`.

- Returns `(to_add, to_remove)`. `new = get_status_tag(status)`; the opposite tag is `fail_tag` when `status` is `"PASS"` and `pass_tag` otherwise.
- `tags` is a list (current tags): `to_add = [new]` only if `new` not in `tags`; `to_remove = [opposite]` only if `opposite` in `tags`.
- `tags` is `None` (current tags unknown): `to_add = [new]` and `to_remove = [opposite]`, both unconditional.
- `update_tags` is unchanged. Nothing is imported into `nacc_common` that it does not already have, except `Tuple` and `Optional` from `typing`.

**No existing gear is refactored.** `phi_image_removal`, the four gears with their own PASS/FAIL tag swap (`redcap_image_form_creator`, `redcap_image_form_importer`, `phi_coordinator`, `form_qc_coordinator`) and `SubjectAdaptor` keep their local copies. Moving them onto `replace_in_acquisition`, `tag_changes` and a shared info-merge helper is a later follow-up, after this gear exists.

### `run.py`

`LoniReceiptMetadataVisitor(GearExecutionEnvironment)`:

- `__init__(*, client: ClientWrapper, file_input: InputFileWrapper, gear_name: str, dry_run: bool)`.
- `create(context, parameter_store=None)`: `wrapper = ContextClient.create(context)` (`wrapper.get_proxy()` feeds the resolver and `wrapper.client` feeds the tagger), `InputFileWrapper.create("input_file", context)` (assert non-None as other gears do), `dry_run = bool(context.config.opts.get("dry_run", False))`, `gear_name = cls.get_gear_name(context, "loni-receipt-metadata")`.
- `run(context)`:
  1. Open `Path(file_input.filepath)` with `encoding="utf-8-sig", newline=""` and call `parse_receipt(file_input.filename, stream)`. `ReceiptError`, `OSError` or `UnicodeDecodeError` raise `GearExecutionError` (fatal, before any write).
  2. Build the resolver and tagger: real or dry variants chosen by `self.__dry_run`.
  3. `result = ReceiptProcessor(receipt, resolver).run()`.
  4. If not `result.passed`, log the failure summary at error (count of failed rows) before tagging, so a tag failure cannot hide it.
  5. `tagger.mark(result.passed)`.
  6. If not `result.passed`, raise `GearExecutionError` with the count of failed rows. `GearEngine.run` logs it and exits with code 1 (Requirement 5.3).
- `main()`: `GearEngine().run(gear_type=LoniReceiptMetadataVisitor)`, as in `pipeline_event_logger` (no parameter store).

The copy's file name is `file_input.filename` (the Input_Receipt's name, Requirement 4.3). The input file ID is `file_input.file_id`.

## Data Written

`acquisition.info.upload_loni.<file_id>` for the multi-echo sample, with fake values:

```json
{
  "<24-hex file id>": {
    "file_name": "00002-CLARiTI_Accelerated_Sagittal_MPRAGE_MSV22.dicom.zip",
    "upload_id": "CLARITI_ADC00-1790000000001",
    "status": "ARCHIVED",
    "uploads": [
      {"loni_uid": "I10000001", "upload_date": "2026-09-21 09:14:51"},
      {"loni_uid": "I10000002", "upload_date": "2026-09-21 09:14:54"}
    ]
  }
}
```

`file_name` is the Flywheel file's own name (from `get_file`), not derived from the directory.

## Edge Cases

- One receipt spanning several acquisitions of a session: handled by grouping on `acquisition_id`; each acquisition gets its own info write and copy.
- Several files in one acquisition: one copy holds the rows of all of them; one `update_info` call writes all their entries.
- Mixed Upload (some rows successful, one failed): no entry for that file ID; its rows still appear in the copy if the acquisition has another entry; job fails.
- Failed-only receipt (the failed sample has no `LONI UID` or `Upload Date` columns): accepted, every row failed, no writes, tag FAIL, job fails.
- Re-run of the same receipt: entries and the copy are replaced with identical content (new file version, or delete-and-upload under the 409 fallback); the tag is reset to the current outcome.
- Re-run after a partial failure: converges, because writes are idempotent replacements.
- Copy attach fails after the entries were written: the entries stay, all rows of that acquisition count as failed, the job fails and the receipt is tagged `-FAIL`. A re-run replaces the entries with identical content and retries the copy.
- Entry already present for a file ID from an earlier receipt (re-upload): replaced; other IDs untouched.
- Same file ID appearing in two receipts: the later run replaces the earlier entry, and the copy named after that receipt is a different file name, so the acquisition holds both copies.
- Deleted file ID: whether `get_file` returns 404 or a record is not verified, and the SDK `FileEntry` has no `deleted` attribute. The resolver does not rely on it: the file counts as resolved only if the acquisition's reloaded `files` list contains that file ID. Otherwise the Upload's rows are Failed_Rows (Requirement 2.4).
- Receipt copy name collisions: the input receipt is expected to be an analysis output file of `loni-upload`, so the copy (in an acquisition) never replaces it. `InputFileWrapper` would also accept a receipt stored in an acquisition; if someone runs the gear on a receipt stored in one of the acquisitions it writes to, the same-name copy replaces the input. That case is not supported and not guarded against. No claim is made about how `loni-upload` selects files for upload.

## Error Handling Summary

| Operation | Failure | Class | Caller receives | Logging |
|---|---|---|---|---|
| Read/parse receipt | Missing required columns, undecodable/unreadable file | Fatal | `GearExecutionError`, exit 1, no writes, no tag | error |
| `get_file` / `get_acquisition` | `ApiException`, or file not in an acquisition | Recoverable (row-level) | Rows of that Upload counted failed; processing continues | warning per row with file ID and status |
| Row check | Non-success status, blank Upload ID, blank/absent LONI UID or Upload Date, no file ID in Directory | Recoverable (row-level) | Counted failed; no entry for that Upload | warning per row (file ID or raw Directory, status) |
| `write_upload_loni` / `attach_receipt_copy` | `TargetWriteError` (from `ApiException` after 3 retries) | Recoverable (acquisition-level) | All rows of the acquisition become Failed_Rows; other acquisitions continue | error with acquisition label, warning per row |
| Tag the input receipt | `ApiException` | Fatal for the step (job fails; writes already done stay) | `GearExecutionError`, exit 1 | error |
| Any Failed_Row | n/a | Job outcome | Summary logged, then tag, then `GearExecutionError`, exit 1 | error summary |

Unexpected non-API exceptions propagate and crash the job without a tag. These indicate bugs.

## Invariant Ownership

| Invariant | Enforced in | Reason |
|---|---|---|
| Required columns present | `receipt.parse_receipt` | The receipt format is a property of the input, and the check must run before any Flywheel call |
| Row success definition and Upload grouping | `receipt.ReceiptRow` and `ReceiptProcessor` | Pure logic with no Flywheel dependency, testable directly |
| Nothing written for an Upload with a row-level failure (non-success row, unresolved ID). Exception: if the copy attach fails after the entries were written, the entries stay | `ReceiptProcessor` (the entry is built only when no row failed) | Single place that decides what is written; targets stay dumb |
| Other file IDs' entries preserved | `FlywheelAcquisitionTarget.write_upload_loni` | Only the target knows how `update_info` behaves |
| No write in dry run | `run.py` (chooses dry implementations) | Keeps `main.py` free of flags; tests assert the dry classes make no SDK write calls |
| Tag set before the job fails | `run.py` ordering (`mark`, then raise) | The exit code is a gear-interface concern |

## Build and Repository Changes

- `common/src/python/uploads/acquisition.py`: add `replace_in_acquisition` and the private `_delete_file` (see "Shared additions"). Tests: `common/test/python/uploads/test_acquisition.py` (existing file, new cases). Run that whole file, which covers `upload_to_acquisition`, plus the tests of its other users: `pants test common/test/python/uploads::` and the gear tests that import `uploads.acquisition` (found with `pants dependents common/src/python/uploads/acquisition.py`).
- `nacc-common/src/python/nacc_common/error_models.py`: add `GearTags.tag_changes`. Tests: new `nacc-common/test/python/test_gear_tags.py`, in the existing flat `nacc-common/test/python` layout (the module name is unique there, so no `Duplicate module` conflict). Run the whole `nacc-common/test/python::` directory, since `error_models.py` is imported by most of it, and the tests of gears that use `GearTags` (`dicom_qc_checker`, `image_identifier_lookup`, `form_qc_checker`, `form_qc_coordinator`).
- `common/src/python/test_mocks/mock_flywheel.py`: additive extension of the shared mocks (see Testing). Existing tests must keep passing. Run `gear/form_scheduler` tests, the only other user of `MockAcquisition` and `MockFlywheelProxy`.
- `ruff.toml`: add `loni_receipt_metadata_app` and `loni_receipt_metadata_test` to `known-first-party`, in sorted position after `loni`. Verify with the regeneration command in the `[lint.isort]` comment.
- Run `pants tailor` and then `pants fix` per file (file scope), `pants lint`, `pants check`, `pants test` on the gear; full quality check at the end (`.kiro/steering/devcontainer.md`).
- Documentation is not required by the requirements and is out of scope. No `docs/loni_receipt_metadata/index.md` page and no `mkdocs.yml` nav entry are added. No `CHANGELOG.md` and no version bumps (`versioning.md`).
- All imports at the top of each file. Tests live in `loni_receipt_metadata_test/` with an empty `__init__.py`.

## Testing

Fixtures: the sample receipts contain real subject IDs and are not stored in the repo. Tests must not read or copy them verbatim. Create sanitized copies in `gear/loni_receipt_metadata/data/`: a successful single-acquisition receipt, a multi-echo receipt (several rows per file ID), a multi-acquisition receipt (rows resolving to two acquisitions), a failed receipt (no `LONI UID`/`Upload Date` columns, blank `Upload ID`, status `Duplicate files`), and a mixed receipt. Replace subject IDs with fake values (e.g. `ptid0001+NACC000001`), upload IDs with `CLARITI_ADC00-<fake>`, LONI UIDs with `I1000000x`, file IDs with fake 24-hex strings, and remove free-text notes. The gear's `data/.gitignore` ignores everything except listed names (as in `pipeline_event_logger/data/.gitignore`), so list each fixture as an exception.

Unit tests (no Flywheel):

- `test_receipt.py`: header validation naming each missing column; duplicate header; long row; short row padding; BOM; header-only receipt; file ID extraction (zip-named directory, plain file path, no prefix, uppercase hex rejected, `_` required); `is_successful`/`is_failed` for each condition; `to_csv` keeps header and column order and quoting, includes only the given rows.
- `test_main.py` with a fake `FileResolver` and a recording `AcquisitionTarget` (a reusable fixture in `conftest.py`): multi-echo Upload gives one entry with all UIDs in order; two acquisitions give two writes and two copies with the right rows; mixed Upload gives no entry, copy still contains its rows when the acquisition has another entry; unresolved ID fails its rows; acquisition with only failed Uploads gets no write and no copy; all Uploads processed before the result is returned; warnings carry file ID and status; a target that raises `TargetWriteError` makes every row of that acquisition a Failed_Row (warning per row, no PASS) and later acquisitions still run; a target whose `attach_receipt_copy` raises after `write_upload_loni` succeeded: the recording target still holds the `write_upload_loni` call, all rows of that acquisition are counted failed, and the result is not passed; first-row `upload_id`/`status` with a warning on mismatch.
- Required shared-mock extension (decided, per requirements.md; option (b), gear-local `Mock(spec=...)` fixtures, is rejected). In `common/src/python/test_mocks/mock_flywheel.py`:
(1) `MockFile.__init__` gains optional `file_id: str = ""` and `acquisition_id: str = ""`. It passes `file_id=file_id or None` and `parents=MockParents(acquisition=acquisition_id or None)` through to `FileEntry`; if `FileEntry` (a pydantic model) rejects the `parents` type, `MockFile` sets `file_id` and `parents` as plain attributes or properties instead, the same way it already handles `modified`. The resolver reads `file.parents.acquisition` and `file.file_id`, so both must be populated. `MockParents` already has an `acquisition` field. A new helper `create_mock_acquisition_file(name, file_id, acquisition_id)` returns such a `MockFile`; the gear tests use it instead of `create_mock_file_with_parent`, which only sets `parent_ref` (an attribute the SDK `FileEntry` does not have) and is left unchanged.
(2) `MockFlywheelProxy` gains `get_file(file_id)` and `get_acquisition(acquisition_id)` overrides (the inherited methods need a real client, and `__init__` does not call `super().__init__`). `get_acquisition` returns the registered `MockAcquisition` from `_containers`. `get_file` looks up files by `file_id` in a new `_files` dict filled by `add_file(file)`, and raises `flywheel.rest.ApiException(status=404)` for an unknown ID. Tests register a file with `add_file` and also append it to its `MockAcquisition.files`, so the check on `reload().files` passes; a deleted-file test registers the file with the proxy only.
(3) `MockAcquisition` declares these as pydantic fields with defaults: `info: Dict[str, Any] = {}`, `uploads: List[Any] = []`, `deleted: List[str] = []`, `conflict_on_upload: bool = False`. `reload()` returns `self.model_copy(deep=True)`, a detached copy, like the SDK (the shared mock currently returns `self`, which hides stale-object bugs; no existing test depends on identity, and the change keeps existing tests passing, to be confirmed by running them). Methods: `update_info(info)` (`self.info.update(info)`, which replaces each top-level key like the real behavior), `upload_file(file_spec)` (raises `ApiException(status=409)` when `conflict_on_upload` is true and the name already exists in `files`, otherwise appends the spec to `uploads`), `delete_file(name)` (removes the file from `files` if present, appends the name to `deleted`, and clears `conflict_on_upload` so the re-upload succeeds).
Existing tests must keep passing; all additions are new fields, attributes and methods with defaults. The tagger tests use a `unittest.mock.Mock(spec=flywheel.Client)` named `mock_client` from the gear's `conftest.py`, with `get_file`, `add_file_tags`, `delete_file_tags` configured per case (the shared mocks have no SDK `Client` mock). No separate tests are added for the mock extension; the gear tests exercise it.
- Shared-module tests (written in the shared modules' own test packages, not the gear's):
  - `common/test/python/uploads/test_acquisition.py`, using the extended `MockAcquisition`: `replace_in_acquisition` uploads once when no conflict; on a 409 it deletes the name then uploads again (`deleted` holds the name, `uploads` holds the spec); a non-409 `ApiException` propagates without a delete; a failing delete or failing second upload propagates; `upload_to_acquisition` tests are unchanged and still pass.
  - `nacc-common/test/python/test_gear_tags.py`: `tag_changes` with a list lacking both tags (add only), holding the opposite tag (add and remove), already holding the new tag (no add), holding both; with `None` (add and remove, unconditional); for `"PASS"` and `"FAIL"`; the input list is not mutated; `update_tags` behavior is unchanged.
- `test_flywheel_io.py` using `MockFlywheelProxy` / `MockAcquisition` from `test_mocks` as extended above: resolver returns `None` for `ApiException`, for a non-acquisition file, and for a file ID absent from `acquisition.reload().files` (deleted file); one acquisition object cached per ID; target merge preserves other file IDs and replaces the same ID; two sequential `write_upload_loni` calls on the same target (second call sees the first call's entries, because `update_info` mutates the stored object and `reload` returns a deep copy); resolver passes the reloaded acquisition to `target_factory`; target converts `ApiException` to `TargetWriteError`; `upload_file` receives a `FileSpec` with the original name and `text/csv`; tagger makes the SDK calls given by `tag_changes` (opposite tag removed, new tag added, no duplicate); tagger `current is None` path (`get_file` raises `ApiException`): unconditional delete of the stale tag then add, an `ApiException` from that delete is ignored, an `ApiException` from `add_file_tags` raises `GearExecutionError`; `attach_receipt_copy` passes a `FileSpec` to `replace_in_acquisition` and converts an escaping `ApiException` to `TargetWriteError` (the 409 logic itself is tested in `test_acquisition.py`); dry-run classes call no write method and log the copy contents.
- `test_run.py` in the style of `pipeline_event_logger_test/test_run.py`: `create` uses `ContextClient` (not a parameter store), reads `dry_run`; `run` logs the summary, tags, then raises on failure; bad receipt raises `GearExecutionError` before any resolver call.

Integration (manual, dev environment, covered by acceptance, not automated):

- M3: upload the same-name CSV to a dev acquisition twice (run the gear twice on one receipt) and confirm one file with a new version, or the 409 fallback path.
- M1: run with `dry_run=true` on a sanitized-equivalent receipt and confirm the logs and no Flywheel change.
- M2: run on a real dev receipt as a normal user, then confirm `acquisition.info.upload_loni`, the receipt copy and the tag on the analysis file. This also confirms the permission assumption for item (d). Run the failed sample to confirm the FAIL tag and exit code 1.

Property-style tests are not needed; the logic is small and example-driven.

## Out of Scope (restated)

Gear-rule start, defaced UID retrieval, a distinguished UID, any change to `loni-upload`, reformatting of dates, a docs page and nav entry, version bumps and CHANGELOG entries.

