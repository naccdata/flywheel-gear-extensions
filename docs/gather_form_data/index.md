# Gather Form Data

This gear takes a CSV file containing a list of participants across centers, gathers form data for each and writes files for each module.

## Input file

The input file must have a column named `naccid` with the NACCID for each participant.

Note: use the [identifier-lookup](../identifier_lookup/) gear if your input source only has `adcid`, `ptid`.

So, an input file will look like

```csv
"naccid"
"NACC000001"
"NACC000002"
```

but may have other columns.

## Gear configuration

The gear manifest config includes the following parameters

- `project_names` - Default `"ingest-form"`.
  A string containing a comma-separated list of project names to search.
- `include_derived` - Default `false`.
  A Boolean indicating whether to include derived variables or missingness information.
- `modules` - Default `"UDS,FTLD,LBD"`
  A string containing a comma-separated list of form module names to be included.
- `study_id` - Default `"adrc"`.
  Should be set if any participants have data from an affiliated study.

## Output

A file is written for each module for which participant data is found.
Columns depend on the module and whether `include_derived` is `true`.

File names have the format `<study-id>-<module-name>-<date>.csv`.
For instance, `allftd-uds-10-20-2025.csv`.