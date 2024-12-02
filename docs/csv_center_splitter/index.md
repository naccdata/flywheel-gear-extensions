# CSV Center Splitter

Splits a CSV of participant data by ADCID, and writes the results into projects for the corresponding centers.

## Input Format

Along with the input CSV, the gear takes in a config YAML with the following fields:

```yaml
adcid_key: <column name from the input CSV with the ADCID>
target_project: <name of the target Flywheel project to write results to per center>
delimiter: <delimiter of the CSV, defaults to ','>
```

The ADCIDs are mapped to the Flywheel group ID using the custom info found in the `metadata` project.

### Config Example

```yaml
adcid_key: ADCID
target_project: distribution-ncrad-biomarker
```