# CSV Center Splitter

Splits a CSV of participant data by ADCID, and writes the results into projects for the corresponding centers.

## Input Format

Along with the input CSV, the gear takes in a config YAML with the following fields:

```yaml
adcid_key: <column name from the input CSV with the ADCID>
target_project: <name of the target Flywheel project to write results to per center>
staging_project_id: <ID of the staging Flywheel project to stage results to; will override target_project if specified>
allow_merged_cells: <whether or not to allow merged cells in the input CSV>
delimiter: <delimiter of the CSV, defaults to ','>
local_run: <true if running on a local input file>
```

Some additional notes:
* The ADCIDs are mapped to the Flywheel group ID using the custom info found in the `metadata` project.
* If `staging_project_id` is specified, it will write _all_ split files for to the specified staging project _instead_ of the `target_project` per center, effectively overriding the former. This can be used for preliminary review/testing

### Config Example

```yaml
adcid_key: ADCID
target_project: distribution-ncrad-biomarker
allow_merged_cells: true
```
