# Dataset Aggregator

Aggregates most recent FW datasets across centers. Removes duplicates caused by transferred participants.

Results get written to `{output_prefix}/%Y%m%d-%H%M%S` for each table, e.g.

* `my-bucket/target-prefix/20260206-100129`
* `my-bucket/target-prefix/20260206-100129/my-table/aggregate_result.parquet` for a specific table

A provenance file `provenance.json` is also written at the top level (e.g. `my-bucket/target-prefix/20260206-100129/provenance.json`) that dumps information about the gear that generated the data.

## Workflow

1. Look up the target project for each center in the center mapping
2. Grab the dataset information defined in `project.info.dataset`
3. Find the latest version and tables of each dataset. This is done by querying and inspecting all the `dataset_description.json` files from each version and keeping track of the latest one.

Then for each grouping, perform the download aggregation per table.

> Note we perform an entire `download -> aggregate -> clean -> upload` loop once per table. This is due to the fact that the resulting parquets tend to be exceptionally large, and at the cost of some efficiency it's better to process each table one at a time and clean up as we go instead of trying to process all of them at once, otherwise you risk OOMs. In general much of this code was written to prioritize memory over efficiency.

For each table:

1. Stream and append each center's data for that table (if it exists) into an open file handler.
2. Inspect the aggregated table for transfer duplicates
    1. If detected, find the current ADCID for all all transfer duplicates by querying the Identifiers API by NACCID
    2. Remove rows corresponding to the old ADCID
5. Upload the aggregated table to S3. The current timestamp will be appended to the output prefix as `{output_prefix}/%Y%m%d-%H%M%S`


## Assumptions

This gear assumes that each aggregated project has a dataset defined for it, which largely amounts to having `dataset` metadata defined in the project's `Custom Information`, or `project.info.datset`. This metadata is used to refer to a Flywheel dataset model that exists in S3 under a registered external storage location. This dataset is generally generated after a project has been run through a FW ETL process.

For example

```
dataset
    bucket: bucket
    prefix: prefix
    storage_id: registered FW storage ID
    storage_label: registered FW storage label. in some new ETLs this is changed to just `label`
    type: storage type (must be S3)
```

Additionally, it assumes all datasets belong to the same bucket, and that the files can be cleanly merged without conflict.

In terms of the FW dataset itself, it assumes there is only one parquet per table.

## Other Notes

Flywheel does have its own library (`fw-dataset`) to access and work with FW datasets. However at the time of writing this package causes multiple versioning conflicts with our current repo, and it was also restricting all read/writes to external storages defined within Flywheel (as opposed to any S3 location, which is more a problem on the output side since we need to write to non-FW storage locations).

As such, we are using a combination of our own `AggregateDataset` and `S3BucketInterface` classes instead.
