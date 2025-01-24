# CSV Center Splitter

Splits a CSV of participant data by ADCID, and writes the results into projects for the corresponding centers.

## Input Format

Along with the input CSV to split, the gear takes in a config YAML with the following fields:

```yaml
adcid_key: <column name from the input CSV with the ADCID>
target_project: <name of the target Flywheel project to write results to per center>
staging_project_id: <ID of the staging Flywheel project to stage results to; will override target_project if specified>
delimiter: <delimiter of the CSV, defaults to ','>
local_run: <true if running on a local input file>
dry_run: <whether or not this is a dry run - if so, will do everything except upload to Flywheel>
```

Some additional notes:

* The ADCIDs are mapped to the Flywheel group ID using the custom info found in the NACC admin `metadata` project.
* If `staging_project_id` is specified, it will write _all_ split files to the specified staging project _instead_ of each center's `target_project`, effectively overriding the former. This can be used for preliminary review/testing

### Config Example

```yaml
adcid_key: ADCID
target_project: distribution-ncrad-biomarker
```
