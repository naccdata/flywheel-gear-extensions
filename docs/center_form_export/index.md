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
| `include_derived` | boolean | `false` | no | Whether to include derived variables |
| `formver_split` | boolean | `false` | no | Split output CSVs by form version |
| `batch_size` | integer | `100` | no | Number of subject ids per query batch (see Performance) |
| `reload_workers` | integer | `10` | no | Concurrent workers used to reload each batch's files (see Performance) |

## Output

A CSV file is written for each module for which subject data is found. Columns depend on the module and whether `include_derived` is `true`.

### Filename Patterns

When `formver_split` is **disabled** (default), one file is produced per module:

```
{study_id}-{module_name}-{YYYY-MM-DD}.csv
```

Example: `adrc-UDS-2025-06-15.csv`

When `formver_split` is **enabled**, one file is produced per (module, form version) pair:

```
{study_id}-{module_name}-{formver_label}-{YYYY-MM-DD}.csv
```

Example: `adrc-UDS-v4-2025-06-15.csv`

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
