# REDCap Error Checks Import

Bulk imports error checks into REDCap.

The error check CSVs are created and uploaded to [uniform-data-set](https://github.com/naccdata/uniform-data-set), which are then reorganized and stored in [s3://nacc-qc-rules/CSV/](https://us-west-2.console.aws.amazon.com/s3/buckets/nacc-qc-rules?region=us-west-2&bucketType=general&prefix=CSV/&showversions=false). The gear then pulls the CSVs from S3 to perform the import to REDCap.

## Input Arguments

This gear takes in the following inputs. None are explicitly required and will use the listed default if not provided.

| Field | Default | Description |
| ----- | ------- | ----------- |
| `checks_s3_bucket` | `nacc-qc-rules` | The S3 URI containing the error check CSVs; expects files to be under `CSV/<MODULE>/<FORM_VER>/<PACKET>/form_<FORM_NAME>*error_checks_<TYPE>.csv`. The one exception is the enrollment form, which does not have a packet and has a different filename. |
| `qc_checks_db_path` | `/redcap/aws/qcchecks` | AWS parameter base path for the target REDCap project to import error checks to |
| `fail_fast` | `true` | Whether or not to fail fast during import - if set to true, any error check CSV that fails import will halt the gear |
| `modules` | `all` | The list of modules to perform the import for. If `all`, will run for every module directory found under `<checks_s3_bucket>/CSV` |
| `dry_run` | `false` | Whether or not this is a dry run. If true, will pull and read the error checks but will **not** import them into REDCap |
