# Gather-Submission-Status Gear

This gear takes a CSV file containing a list of participants and generates a CSV file that depending on the configuration either contains the status of form submissions for the participants, or the errors for the form submissions.

## Input file

The input file should have the following columns:

- `adcid`: the ADCID for the center where the participant data is collected. An integer.
- `ptid`: the center assigned participant ID for the participant. A string.
- `study`: the name of the study in lowercase. A string.

An input file would look like

```csv
"adcid","ptid","study"
0,"123456","adrc"
0,"654321","dvcid"
```

The *study* should be the study for which the data was collected.
For instance, if a participant is enrolled solely in DVCID, the study should be given as `dvcid`.
If the participant is co-enrolled in an ADRC clinical core, the value of study should be `adrc`.
Since, these data streams are kept separate, the qualification is required to find the submissions.



## Gear configuration

The gear manifest config includes the following parameters:

- `study_id` - Defaults to `adrc`. Should be set to a different value if any participants have data from an affiliated study.
  For instance, for participants in DVCID that are not co-enrolled in the clinical core, set this to `dvcid`.

- `project_names` - a string containing a comma-separated list of project prefixes.
  These prefixes are used with the study to create the pattern used to match the label of the projects from which data is gathered.
  By default, this string is set to `"ingest-form"`.

  If `study` from the input file is `"adrc"`, the project `ingest-form` will be used.
  Otherwise, the study is used as a suffix to the label.
  For instance, if study is `"dvcid"`, the project `ingest-form-dvcid` will be used.

- `module` - a string that is a comma-separated list of form modules.
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
