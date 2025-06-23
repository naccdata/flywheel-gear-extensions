# Gather-Submission-Status Gear

This gear takes a CSV file containing a list of participants and data modalities and generates a CSV file containing the status for the participant submissions.

## Input file

The input file should have the following columns:

- `adcid`: the ADCID for the center where the participant data is collected. An integer.
- `naccid`: the NACCID for the participant. A string.
- `study`: the name of the study in lowercase. A string
- `modalities`: the list of file modalities to check. A string with list, quoted and comma-separated.

The "study" should be the primary study for which the data was collected.
So, if the data was collected for DVCID, the study should be given as `dvcid`.
If the participant is co-enrolled and the data was collected for the ADRC clinical core, the value of study should be `adrc`.

At the moment, the modalities are form modules: UDS, FTLD, LBD.

An input file would look like

```csv
"adcid","naccid","study","modalities"
0,"NACC000000","adrc","UDS,LBD"
0,"NACC000001","dvcid","UDS"
```

## Output file

The output file contains a row for each file that the participant has

- `filename`: the name of the file
- `file_id`: the Flywheel file ID
- `acquisition_id`: the Flywheel acquisition ID
- `subject_id`: the Flywheel subject ID 
- `modified_date`: the date the file was last modified
- `qc_status`: indicates whether the file has passed all of the QC checks

maybe should be

- `naccid`: the participant ID
- `is_file`: indicator whether file exists
- `modality`: file modality
- `modified_date`: the date the file was modified
- `qc_status`: indicator whether the file has passed all of the QC checks