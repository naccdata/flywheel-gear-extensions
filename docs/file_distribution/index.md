# File Distribution

Gear that distributes files to target projects.

## Input Configurations

Along with the file to distribute, the gear takes in the following configuration values:

```yaml
target_project: name of the target Flywheel project to write results to per center
include: comma-delimited list of ADCIDs to include
exclude: comma-delimited list of ADCIDs to exclude
batch_size: number of centers to batch; will wait for all downstream pipelines to finish running for a given batch before writing others
downstream_gears: if scheduling, comma-delimited string of downstream gears to wait for
dry_run: whether or not this is a dry run - if so, will do everything except upload to Flywheel
```

Some additional notes:

* The ADCIDs are mapped to the Flywheel group ID using the custom info found in the NACC admin `metadata` project.

### Config Example

To distribute to all centers except the Sample Center (ADCID 0):

```yaml
target_project: "distribution-ncrad-biomarker"
exclude: "0"
```
