# Gather Form Data

This gear gathers form data for participants across centers and writes files for each module.

It takes a CSV file listing participants and gathers data for each.

## Input

The gear requires an `input_file` input — a CSV file with a column named `naccid` containing the NACCID for each participant.

Note: use the [identifier-lookup](../identifier_lookup/) gear if your input source only has `adcid`, `ptid`.

Example input file:

```csv
"naccid"
"NACC000001"
"NACC000002"
```

The file may have other columns.

## Gear Configuration

The gear manifest config includes the following parameters:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `project_names` | string | `"ingest-form"` | Comma-separated list of projects to search for form data |
| `include_derived` | boolean | `false` | Whether to include derived variables or missingness information |
| `modules` | string | `"UDS,FTLD,LBD"` | Comma-separated list of form module names to include. Valid values: `UDS`, `FTLD`, `LBD` |
| `study_id` | string | `"adrc"` | The study ID. Should be set if any participants have data from an affiliated study |
| `formver_split` | boolean | `false` | Split output CSVs by form version. When enabled, output is split by form version producing files named `{study_id}-{module}-{formver_label}-{date}.csv` |
| `dry_run` | boolean | `false` | Whether to do a dry run |
| `apikey_path_prefix` | string | `"/prod/flywheel/gearbot"` | AWS parameter path prefix for apikey |

## File Metadata and Tagging

The gear updates the input file with the following metadata after processing. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

1. **QC Result**: A validation QC result is added to the file's `file.info.qc` metadata with:
   - `name`: `"validation"`
   - `state`: `"PASS"` or `"FAIL"` depending on whether all participant lookups succeeded
   - `data`: List of `FileError` objects with error details if any errors occurred

2. **File Tag**: The gear name is added as a simple tag to the input file, indicating the file has been processed by this gear.

## Output

A file is written for each module for which participant data is found.
Columns depend on the module and whether `include_derived` is `true`.

File names have the format `{study_id}-{module_name}-{date}.csv`.
For instance, `allftd-uds-10-20-2025.csv`.

When `formver_split` is enabled, output is split by form version, producing one file per module/version pair: `{study_id}-{module_name}-{formver_label}-{date}.csv`. Each file has a column set restricted to that exact form version; rows are not column-unioned across versions.
