# DBT Runner

Runs `dbt` (data build tool) projects on parquet files pulled from S3, and writes the transformed results back to S3.

## Inputs

The gear takes a `dbt_project_zip` which should contain a full DBT project. Most of our DBT projects are stored in the [dbt-projects](https://github.com/naccdata/dbt-projects) repo.

See the [FW docs for getting started with DBT] for setting up a DBT project.


## Configurations

| Name | Description | Example |
| - | - | - |
| `source_prefixes` | JSON string of the target local directory name to source S3 prefixes | See below |
| `output_prefix` | Location to write results of the DBT execution to | `my-bucket/some-path/results` |
| `dry_run` | Whether or not to do a dry run. Will pull from S3 and run DBT but will not write results back to S3 | |
| `apikey_path_prefix` | The instance specific AWS parameter path prefix for apikey; required for the gear to interact with S3 | `/sandbox/flywheel/gearbot` |
| `debug` | Whether to turn on more verbose logging. Note this includes boto3 logs which are quite dense | |


### source_prefixes

The main input of this gear is a JSON string of the source S3 prefixess, e.g.

```json
{
    "table1": "my-bucket/some/path/to/parquet/files",
    "table2": "my-other-bucket/some-other-path-to-parquet-files"
}
```

and in JSON string form:

```json
"{\"table1\": \"my-bucket/some/path/to/parquet/files\",\"table2\": \"my-other-bucket/some-other-path-to-parquet-files\"}"
```

Note FW will handle escaping characters if kicking off directly through the FW UI, so you can just enter

```json
{"table1": "my-bucket/some/path/to/parquet/files","table2": "my-other-bucket/some-other-path-to-parquet-files"}
```

Do not include the `s3://` prefix nor the trailing `/` in your specified prefixes. Additionally, the keys should only contain alphanumeric characters, with `-`, or `_` allowed in the middle, as these keys will be used as directory names. More specifically, it must match the regex `^[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?$`. Keys should also be unique, otherwise the parquet files may clobber each other.

The gear will glob for `*.parquet` files under the specified S3 path (recursively), and pulls them to a local directory under `source_table` based on the key name. For example, given the above input:

```
source_data/
    table1/
        a.parquet
    table2/
        b.parquet
        c.parquet
```

If the source parquets are nested under the S3 path, the hierarchy will be preserved when it is downloaded to the local directory:

```
source_data/
    table1/
        a.parquet
    table2/
        b.parquet
        nest1/
            nest2/
                c.parquet
```

The `dbt_project_zip` project can then assume that the `source_data` directory lives parallel to the DBT project, and can specify the source parquets as an external location, e.g. `../source_data/table1/*.parquet` or `../source_data/table2/nest1/nest2/c.parquet`. These are usually defined in `models/sources.yml`.
