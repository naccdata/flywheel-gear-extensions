# Center Form Export

This gear exports form data for all subjects in a Flywheel group/project without requiring a participant list. It is intended for center-level bulk exports.

## How It Differs from gather_form_data

The [`gather_form_data`](../gather_form_data/) gear requires a participant list CSV as input — a file with a column of NACCIDs identifying which participants to process.

The `center_form_export` gear instead resolves a Flywheel group and project, then queries each configured module's files in batches of subjects across the whole project — no input file and no NACCID matching required.

Use `center_form_export` when you want to export form data for an entire center project without maintaining a separate participant list.

## Input

The only input is `api-key` (a Flywheel API key). No file input is required.

## Gear Configuration

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `group_id` | string | — | yes | Flywheel group ID for the center |
| `project_name` | string | — | yes | Project label to iterate |
| `modules` | string | `"UDS,FTLD,LBD"` | no | Comma-separated list of module names |
| `study_id` | string | `"adrc"` | no | Study identifier used in output filenames |
| `source_id` | string | — | yes | Identifier of the project being read, used in output filenames (see Source Identifiers) |
| `include_derived` | boolean | `false` | no | Whether to include derived variables |
| `formver_split` | boolean | `false` | no | Split output CSVs by form version |
| `batch_size` | integer | `100` | no | Number of subject ids per query batch (see Performance) |
| `reload_workers` | integer | `10` | no | Concurrent workers used to reload each batch's files (see Performance) |
| `run_id` | string | `""` | no | Caller-supplied identifier appended to output filenames (see Run Identifiers) |

## Output

A CSV file is written for each module for which subject data is found. Columns depend on the module and whether `include_derived` is `true`.

Output is written through the gear context, so it lands in the **job's destination container**, which is independent of the project named by `group_id` / `project_name` — those name the project the gear *reads*. A caller can therefore point several jobs that read different projects at one shared destination project; `source_id` exists so their filenames stay distinct when it does (see Source Identifiers).

The destination must be in the **same group** as the project being read (see Cross-Group Guard).

Every output file is tagged with the gear name (`center-form-export`), so consumers can recognize export artifacts from file tags rather than by matching the filename. Tags are written through the gear context's metadata, which is only flushed when the gear exits cleanly — a failed run's partial output is untagged.

### Filename Patterns

When `formver_split` is **disabled** (default), one file is produced per module:

```
{study_id}-{source_id}-{module_name}-{stamp}.csv
```

Example: `adrc-ingest-UDS-2025-06-15.csv`

When `formver_split` is **enabled**, one file is produced per (module, form version) pair:

```
{study_id}-{source_id}-{module_name}-{formver_label}-{stamp}.csv
```

Example: `adrc-ingest-UDS-v4-2025-06-15.csv`

`{stamp}` is the run date (`YYYY-MM-DD`), followed by `-{run_id}` when a `run_id` was supplied.

### Segment Charsets

Filenames are `-`-delimited and parsed by anchored patterns, so each segment is constrained:

| Segment | Charset | Source |
|---------|---------|--------|
| `study_id` | `[A-Za-z0-9]+`, ≤16 | config, validated at startup |
| `source_id` | `[A-Za-z0-9]+`, ≤16 | config, validated at startup |
| `module_name` | `[A-Za-z0-9]+`, ≤16 | config, validated at startup |
| `formver_label` | `v[A-Za-z0-9.]+` or `unknown` | form data, normalized by `formver_label` |
| `run_date` | `\d{4}-\d{2}-\d{2}` | gear clock |
| `run_id` | `[A-Za-z0-9]+`, ≤32 | config, validated at startup |

A malformed config value fails the job at startup rather than producing output no consumer can attribute. Note this happens at job *runtime*, not at job creation — a caller sending a bad value sees a failed job, not a rejected request.

`formver_label` is the one segment permitted a `.`, because real form versions carry one — LBD `v3.1`. It is safe there and only there: the segment is gear-derived, and sits in a fixed, non-final position where a `.` cannot be read as a segment boundary (a `-` or `_` could). Consumers should split the extension from the right (`os.path.splitext`), not on the first `.`.

That segment may also contain letters. `formver_label` refuses only values that would break the name — anything carrying a `-`, `_`, `/`, or whitespace, such as `3.0-draft` — labelling those `unknown` and logging them. A value that is merely unusual rather than unusable, such as `3a`, passes through as `v3a`. The check is for filename safety, not for a well-formed version number, so consumers must accept `v` followed by any letters, digits, and dots.

### Source Identifiers

`source_id` names the project a job read — e.g. `ingest` or `legacy`. It is **required**, and appears in every output filename.

It exists because the read source and the write destination are independent (see Output). When one user-facing export fans out across several source projects and all of those jobs write into one destination project, every other field of the filename is identical by construction: same study, same date, same `run_id`, and the same module and form version wherever the source projects overlap. Without a source segment those jobs write byte-identical names into one project, Flywheel versions the second write over the first, and one job's output is reachable only as an older file version — silently absent from any listing without a version selector.

The value is supplied by the caller rather than derived from `project_name`, so that project-naming conventions stay outside the gear. Deriving it would give a wrong-but-plausible answer for any project whose label doesn't match an expected prefix.

`source_id` sits before the module rather than after the date because the trailing `run_id` is optional. Two optional trailing segments would be unparseable: given `...-2025-06-15-abc123.csv`, nothing tells a consumer whether `abc123` is a run identifier or a source. Placing `source_id` in a fixed position ahead of the date keeps a single, anchorable shape.

Its charset matches `run_id` — letters and digits only, at most 16 characters (see Segment Charsets). This rules out passing a raw project label such as `ingest-form-adrc`. A malformed or empty value fails the job at startup.

`study_id` is kept in the filename even where a per-study destination project makes it redundant, because these CSVs are downloaded and spend the rest of their lives outside Flywheel, where the project name is gone and the filename is the only remaining label.

### Run Identifiers

By default filenames are stamped with the run date alone, which has day granularity: a second export of the same modules on the same day writes the same filenames, so Flywheel replaces the files in place. The previous version is retained by Flywheel but is not reachable through interfaces that have no version selector, and nothing in the filename distinguishes one run from another.

Passing `run_id` adds a caller-chosen segment after the date. Two exports on the same day then produce distinct files, and all files of one run — including files written by *separate* jobs, when a caller fans one user-facing export out across several projects — carry the same identifier and can be grouped by it.

`run_id` must contain only letters and digits, and be at most 32 characters. Because filenames are `-`-delimited and parsed by anchored patterns, a `run_id` containing `-`, `.`, or `_` would make the trailing segments ambiguous; a malformed value fails the job at startup rather than silently producing an unparseable filename. A compact UTC timestamp such as `20260724T210431` satisfies the charset and sorts naturally.

The run date and the `run_id` are both fixed once per gear run, not per output file. Output is written as each module finishes gathering, which on a large export can be minutes apart and can cross midnight — so a value read from the clock at write time would differ between modules and split one run's files across several apparent runs.

Omitting `run_id` reproduces the date-only filenames exactly, with no trailing separator.

## Cross-Group Guard

Before resolving the source project or gathering anything, the gear compares the group owning the job's **destination container** with the `group_id` in config. If they differ, the job fails with a `GearExecutionError` and writes no output.

This exists because the gear reads whatever `group_id` / `project_name` its config names, using GearBot's API key, which can read every center. Nothing in the job itself constrains that to the caller's own center. Without the check, anyone able to launch the gear could point it at another center's `ingest-form` project and have that center's records written as CSVs into a project they can download from.

The check runs first, so a refused run resolves nothing, reads nothing, writes nothing, and reveals nothing about the project it was aimed at. It **fails closed**: a job whose destination cannot be identified or resolved, or whose destination container reports no group, is refused rather than allowed through unchecked.

Only the group is compared. Study-level scoping — an `adrc` export landing in a `distribution-form-dvcid` project — is left to the caller, since only the caller knows which study a run belongs to.

This is defense in depth, not a replacement for Flywheel permissions. It closes the cross-center path for every trigger mechanism, so it holds regardless of how job-launch rights are granted.

## Performance

Each module's files are fetched in batches of subjects (`batch_size` config, default 100) rather than one query per subject or a single unscoped query for the whole project — the latter was tried and found to reliably time out on Flywheel's backend for large centers (tens of thousands of files). Batching keeps query count low while keeping each individual query narrowly scoped.

Within each batch, files are `.reload()`ed (to populate their form data) concurrently across a shared worker pool (`reload_workers` config, default 10) rather than one at a time, since this was found by benchmark to be the dominant remaining cost for modules with many visits per subject (e.g. UDS) — batching alone only reduces query *count*, not the per-file reload cost, which scales with total matching files regardless of how subjects are grouped.

Validated end-to-end against a large real NACC center (Arizona's `retrospective-form` project, 3,003 subjects, ~13,980 sessions — used as a demanding test case, not confirmed to be the largest center overall): 16m10s vs. an earlier ~1h52m baseline with the original per-subject design (~6.9x faster), with byte-comparable output.

The `batch_size=100` default was validated, not guessed: a sweep across 25/100/200 against both a small center and `retrospective-form` showed 25 was slower everywhere (more query round-trips), and 200 was faster on the small center but a wash on `retrospective-form` (reload volume, not query count, dominates total time there) — and, importantly, 200 did not reproduce the earlier timeout, indicating 100 has real margin rather than sitting at a fragile edge. If a different center's data shape performs poorly with these defaults, both are overridable via gear config without a code change.

The gear logs progress once per module and once per subject batch processed, so a long-running job's progress can be distinguished from a stalled one in the job log.

## Error Handling

If an individual file fails during processing, the gear logs a warning with the error message and continues processing the remaining files in that module and the remaining modules. A single data issue does not block the entire export.

Each module's output is written to disk as soon as that module finishes gathering, before the next module starts — not held until every module has gathered. If a module hits an unrecoverable error (e.g. a persistent connection failure, not an individual file's data issue), that error propagates and the gear halts, but any modules that already finished are unaffected: their output is already on disk. The module that failed, and any modules after it, produce no output for that run.

Concurrent `.reload()` calls within a batch share one Flywheel client/HTTP session across worker threads. This has been observed correct in all testing to date (including the full run against `retrospective-form`, ~25k files, with no signs of data corruption), but is not a guarantee documented by the underlying Flywheel SDK — a known, accepted assumption rather than a verified one.
