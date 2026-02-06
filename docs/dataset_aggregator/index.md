# Dataset Aggregator

Aggregates most recent FW datasets across centers. Removes duplicates caused by transferred participants.

Results get written to `{output_prefix}/{timestamp}`, e.g. `my-bucket/target-prefix/`

## Workflow

1. Look up the target project for each center in the center mapping
2. Grab the dataset information defined in `project.info.dataset`
3. Group the found datasets by bucket; it is generally assumed all datasets live in the same bucket, but this is done to handle the case they aren't.

Then for each grouping, perform the download aggregation:

1. Find the latest version of each dataset; this is done by querying and inspecting all the `dataset_description.json` files from each version
2. Iterating over the latest versions, download and aggregate each table into an open file handler. When a table is encountered for the first time, a new file handler is opened for it.
    1. Once a center has been aggregated, its data is cleaned up immediately to free up disk space
3. Once all datasets have been downloaded, close the file handlers
4. Inspect the aggregated tables for transfer duplicates
    1. If detected, find the current ADCID for all all transfer duplicates by querying the Identifiers API by NACCID
    2. Remove rows corresponding to the old ADCID
5. Upload final tables to S3; the current timestamp will be appended to the output prefix as `/%Y%m%d-%H%M%S`


## Assumptions

This gear assumes that each aggregated project has a dataset defined for it, which largely amounts to having `dataset` metadata defined in the project's `Custom Information`, or `project.info.datset`. This metadata is used to refer to a Flywheel dataset model that exists in S3 under a registered external storage location. This dataset is generally generated after a project has been run through a FW ETL process.

For example

```
dataset
    bucket: bucket
    prefix: prefix
    storage_id: registered FW storage ID
    storage_label: registered FW storage label
    type: storage type (usually S3)
```

Additionally, it assumes the nature of the files it is aggregating are compatible. For example, one project's UDS parquet table should be able to merge with another center's UDS parquet table without conflicts.

## Other Notes

Flywheel does have its own library (`fw-dataset`) to access and work with FW datasets. However at the time of writing this package causes multiple versioning conflicts with our current repo, and it was also restricting all read/writes to external storages defined within Flywheel (as opposed to any S3 location).

As such, we are instead using a combination of our own `AggregateDataset` and `S3BucketInterface` classes.
