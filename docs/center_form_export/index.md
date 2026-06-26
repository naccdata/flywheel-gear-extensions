# Center Form Export

This gear exports form data for all subjects in a Flywheel group/project without requiring a participant list. It is intended for center-level bulk exports.

## How It Differs from gather_form_data

The [`gather_form_data`](../gather_form_data/) gear requires a participant list CSV as input — a file with a column of NACCIDs identifying which participants to process.

The `center_form_export` gear instead resolves a Flywheel group and project, then iterates all subjects in that project automatically. No input file is needed. Each subject label is treated as a NACCID.

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

## Error Handling

If a subject fails during processing, the gear logs a warning with the subject identifier, module name, and error message, then continues processing remaining subjects. A single data issue does not block the entire export.
