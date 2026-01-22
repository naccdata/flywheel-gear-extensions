# Dataset Aggregator

Aggregates most recent FW datasets across centers.

## Assumptions

This gear assumes that each aggregated project has a dataset defined for it, which largely amounts to having `dataset` metadata defined in the project's `Custom Information`. This metadata is used to refer to a Flywheel dataset model that exists in S3 under a registered external storage location. This dataset is generally generated after a project has been run through a FW ETL process.

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
