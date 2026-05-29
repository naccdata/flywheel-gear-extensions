# Gather Form Data

This gear gathers form data for participants across centers and writes files for each module.

It supports two execution modes:

- **Participant list mode** (default): Takes a CSV file listing participants and gathers data for each.
- **Project mode**: Iterates all subjects in a specified Flywheel group/project.

## Execution Modes

### Participant List Mode

Set `execution_mode` to `"participant_list"` (or leave as default).

Requires the `input_file` input — a CSV file with a column named `naccid` containing the NACCID for each participant.

Note: use the [identifier-lookup](../identifier_lookup/) gear if your input source only has `adcid`, `ptid`.

Example input file:

```csv
"naccid"
"NACC000001"
"NACC000002"
```

The file may have other columns.

### Project Mode

Set `execution_mode` to `"project"`.

Instead of reading from a CSV, the gear resolves a Flywheel group and project, then iterates all subjects in that project. Each subject label is treated as a NACCID.

Requires:

- `group_id` — Flywheel group ID for the center
- `project_name` — Project label to iterate

The `input_file` input is not required in project mode.

## Gear Configuration

The gear manifest config includes the following parameters:

- `execution_mode` - Default `"participant_list"`.
  Either `"participant_list"` or `"project"`.
- `group_id` - Optional.
  Flywheel group ID for the center (required in project mode).
- `project_name` - Optional.
  Project label to iterate (required in project mode).
- `project_names` - Default `"ingest-form"`.
  A string containing a comma-separated list of project names to search for form data (participant list mode only).
- `include_derived` - Default `false`.
  A Boolean indicating whether to include derived variables or missingness information.
  Applies to both execution modes.
- `modules` - Default `"UDS,FTLD,LBD"`.
  A string containing a comma-separated list of form module names to be included.
  Valid values: `UDS`, `FTLD`, `LBD`.
- `study_id` - Default `"adrc"`.
  Should be set if any participants have data from an affiliated study.

## File Metadata and Tagging

In participant list mode, the gear updates the input file with the following metadata after processing. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

1. **QC Result**: A validation QC result is added to the file's `file.info.qc` metadata with:
   - `name`: `"validation"`
   - `state`: `"PASS"` or `"FAIL"` depending on whether all participant lookups succeeded
   - `data`: List of `FileError` objects with error details if any errors occurred

2. **File Tag**: The gear name is added as a simple tag to the input file, indicating the file has been processed by this gear.

Note: In project mode, no input file metadata is updated since there is no input file.

## Output

A file is written for each module for which participant data is found.
Columns depend on the module and whether `include_derived` is `true`.

File names have the format `<study-id>-<module-name>-<date>.csv`.
For instance, `allftd-uds-10-20-2025.csv`.
