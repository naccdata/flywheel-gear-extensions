# Dataset Aggregator

Aggregates most recent FW datasets across centers. Also checks for duplicates based on duplicate criteria, and resolves as specified.

Results get written to `{output_prefix}/%Y%m%d-%H%M%S/tables` for each table, e.g.

* `my-bucket/target-prefix/20260206-100129/tables`
* `my-bucket/target-prefix/20260206-100129/tables/my-table/aggregate_result.parquet` for a specific table

A provenance file `provenance.json` is also written at the top level (e.g. `my-bucket/target-prefix/20260206-100129/provenance.json`) that dumps information about the gear that generated the data.

## Workflow

1. Look up the target project for each center in the center mapping
2. Grab the dataset information defined in `project.info.dataset`
3. Find the latest version and tables of each dataset. This is done by querying and inspecting all the `dataset_description.json` files from each version and keeping track of the latest one.

Then for each table:

1. Aggregate each center's data for that table (if it exists) into an open file handler.
2. Inspect the aggregated table for duplicates
    * Based on the `duplicates_criteria_json` optional configuration file (see [format below](#duplicates-criteria-format)). If provided, two rows are considered a duplicate for a given table if ALL fields in the list match. If a table has no duplicate criteria, all rows will be kept.
    * Each table can specify what to do when duplicates are encountered with the `on_duplicate` field:
        * `drop_all`: Drops all duplicate rows- default if not specified
        * `keep_all`: Keeps all duplicate rows
        * `active_only`: Only keeps rows for the NACCID's current center
    * Dropped rows are reported reported as part of the gear output
5. Upload the aggregated table to S3. The current timestamp and a `tables` directory will be appended to the output prefix as `{output_prefix}/%Y%m%d-%H%M%S/tables`

> Note we perform an entire `download -> aggregate -> clean -> upload` loop once per table. This is due to the fact that the resulting parquets tend to be exceptionally large, and at the cost of some efficiency it's better to process each table one at a time and clean up as we go instead of trying to process all of them at once, otherwise you risk OOMs. In general much of this code was written to prioritize memory over efficiency.

## Duplicates Criteria Format

Example:

```json
{
    "table_name": {
        "criteria": [
            "list",
            "of",
            "fields"
        ],
        "on_duplicate": "active_only"
    },
    "uds": {
        "criteria": [
            "naccid",
            "visitdate"
        ]
    },
}
```

If `on_duplicate` is not specified, it will default to `drop_all`.

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

In terms of the FW dataset itself, it assumes there is only one parquet per table, and that each table has both a `naccid` and `adcid` column (in order to resolve duplicates). This is largely dictated by the data model JSON that was used in the ETL to generate the dataset.

## Other Notes

Flywheel does have its own library (`fw-dataset`) to access and work with FW datasets. However at the time of writing this package causes multiple versioning conflicts with our current repo, and it was also restricting all read/writes to external storages defined within Flywheel (as opposed to any S3 location, which is more a problem on the output side since we need to write to non-FW storage locations).

As such, we are using a combination of our own `AggregateDataset` and `S3BucketInterface` classes instead.
