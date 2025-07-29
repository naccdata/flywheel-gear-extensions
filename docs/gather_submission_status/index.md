# Gather-Submission-Status Gear

This gear takes a CSV file containing a list of participants and generates a CSV file containing the status for form submissions for the participants.

> Note: this gear determines the status of data that is associated with a participant. It will not capture errors earlier in the process for files that consist of lists of participants.

## Input file

The input file should have the following columns:

- `adcid`: the ADCID for the center where the participant data is collected. An integer.
- `naccid`: the NACCID for the participant. A string.
- `study`: the name of the study in lowercase. A string

The "study" should be the study for which the data was collected.
For a participant enrolled solely in DVCID, the study should be given as `dvcid`.
If the participant is co-enrolled and the data was collected for the ADRC clinical core, the value of study should be `adrc`.

So, an input file would look like

```csv
"adcid","naccid","study"
0,"NACC000000","adrc"
0,"NACC000001","dvcid"
```

The gear config includes `project_names`, which a string containing a comma-separated list of project prefixes.
These prefixes are used with the study to create the pattern used to match the label of the projects from which data is gathered.
By default, this string is set to `"ingest-form"`.
If `study` from the input file is `"adrc"`, the project `ingest-form` will be used.
Otherwise, the study is used as a suffix to the label.
For instance, if study is `"dvcid"`, the project `ingest-form-dvcid` will be used.

The gear config also includes `module`, which is a string that is a comma-separated list of form modules.
The default includes UDS, FTLD and LBD.


## Output file

The output file contains a row for each file that the participant has

- `filename`: the name of the file
- `file_id`: the Flywheel file ID
- `module`: the form module
- `naccid`: the NACCID
- `modified_date`: the date the file was last modified
- `visit_date`: the visit date from the file
- `qc_status`: indicates pass/fail status of QC checks
