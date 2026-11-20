# Gather-Submission-Status Gear

This gear takes a CSV file containing a list of participants and generates a CSV file that depending on the configuration either contains the status of form submissions for the participants, or the errors for the form submissions.

## Input file

The input file should have the following columns:

- `adcid`: the ADCID for the center where the participant data is collected. An integer.
- `ptid`: the center assigned participant ID for the participant. A string.

An input file would look like

```csv
"adcid","ptid"
0,"123456"
0,"654321"
```

Note: use the [identifier-lookup](../identifier_lookup/) gear to perform a "reverse" lookup if your source data only has NACCIDs.

## Gear configuration

The gear manifest config includes the following parameters:

- `study_id` - Defaults to `adrc`.
  Should be set to a different value if any participants have data from an affiliated study.
  For instance, for participants in DVCID that are not co-enrolled in the clinical core, set this to `dvcid`.

- `project_names` - a string containing a comma-separated list of project prefixes.
  These prefixes are used with the study to create the pattern used to match the label of the projects from which data is gathered.
  By default, this string is set to `"ingest-form"`.

- `modules` - a string that is a comma-separated list of form modules.
  The default includes UDS, FTLD and LBD.

- `query_type` - a string that is either `"error"` or `"status"` indicating whether to generate an error or status report.


## Output file

Both output files contain a row for each file that the participant has with the columns

- `stage`: the processing stage (aka, the "gear")
- `adcid`: the center ADCID (from the input file)
- `ptid`: the participant PTID (from the input file)
- `module`: the form module
- `visit_date`: the visit date from the file

The status output file also contains the column

- `status`: the PASS/FAIL status of the data

## File Metadata and Tagging

After processing, the gear updates the input CSV file with the following metadata. See the [QC Conventions](../nacc_common/qc-conventions.md) reference for details on the data models and conventions used.

1. **QC Result**: A validation QC result is added to the file's `file.info.qc` metadata with:
   - `name`: `"validation"`
   - `state`: `"PASS"` or `"FAIL"` depending on whether the status/error gathering succeeded
   - `data`: List of `FileError` objects with error details if any errors occurred

2. **File Tag**: The gear name (e.g., `"gather-submission-status"`) is added as a simple tag to the input file, indicating the file has been processed by this gear.

## Requests that produce no output

A participant in the input file produces no output rows if the gear finds nothing to report for them.
The gear records these cases as errors in the QC result of the input file (`file.info.qc`), and they do not change the `PASS`/`FAIL` state.
If a run produces an empty or incomplete output file, check the QC result for these errors.

- `no-projects`: no project for the ADCID matches the `project_names` and `study_id` configuration.
  The message gives the ADCID and the project names that were tried.
  The `adcid` column of the input file is the location.
- `no-qc-logs`: no QC status log file was found for the participant in the projects that were searched.
  The `ptid` field gives the participant, and the message gives the ADCID, the projects searched and the modules searched.
  This occurs when
  - the PTID has no submissions in the matched projects,
  - the PTID does not match the PTID in the QC log file names (leading zeros in the input PTID are ignored), or
  - the participant has submissions only for modules that are not in the `modules` configuration parameter.
  Module names are compared to the module in the QC log file name, ignoring case in the file name only, so the configured values must be upper case.

The gear also logs a warning for each ADCID with the number of requested participants that had no QC status logs.

## Error Report Output

The error report output file contains the columns

- `timestamp` - timestamp for the error generation
- `type` - one of "alert", "error", "warning"
- `code` - error code for UDS
- `message` - error message
- `container_id` - the flywheel specific ID for the file container
- `flywheel_path` - the path of the file in flywheel
- `value` - value found
- `expected` - value expected
- `visitnum` - the visit number in submission
- `naccid` - the naccid for the participant
