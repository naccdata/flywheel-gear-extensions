# Identifier Lookup

The identifier-lookup gear reads participant IDs from a tabular (CSV) input file and checks whether each ID corresponds to a NACCID (the NACC-assigned participant ID). This gear supports two directions: `nacc` and `center`.

If the direction is `nacc`, the input file is assumed to have one participant per row with columns `adcid` (NACC-assigned center ID), and `ptid` (center-assigned participant ID), and will append `naccid` to the output.

If the direction is `center`, the input file is assumed to have one participant per row with a `naccid` column, and will append `adcid` and `ptid` to the output.

The gear outputs a copy of the CSV file consisting of the rows for participants that have NACCIDs, with an added `naccid` column for the NACCID.

If there are any rows where the participant ID has no corresponding NACCID, an error file is also produced.
The error file will have a row for each input row in which participant ID has no corresponding NACCID.

## Event Logging

When processing CSV files in the `nacc` direction with QC logging enabled (i.e., when a `form_configs_file` is provided), the gear will also create submission events for each valid visit row. These events are logged to an S3 bucket for tracking data submissions in the NACC event log system.

Event logging behavior:
- Only occurs when direction is `nacc` and QC logging is enabled
- Creates a submit event for each valid visit row in the CSV
- Events include visit metadata such as center, project, visit date, and packet information
- Event logging failures do not affect the primary identifier lookup functionality
- Events are stored in the configured S3 bucket with environment-specific prefixes

## Environment

This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables within the Flywheel runtime.
The variables used are `AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`.
The gear needs to be added to the allow list for these variables to be shared.

## Configuration

Gear configs are defined in [manifest.json](../../gear/identifier_lookup/src/docker/manifest.json).

### Center Validation Configuration

- **`single_center`** (boolean, default: true): Whether the gear is being run in a pipeline for a single center. When set to `true`, center validation is enabled and all rows in the input file must have the same `adcid` value. When set to `false`, center validation is disabled, allowing files with rows containing different `adcid` values to be processed. This is useful for multi-center data processing scenarios where you still want to use module configurations for field validation.

### Event Logging Configuration

The following configuration parameters control event logging behavior:

- **`environment`** (string, default: "prod"): Environment for event logging. Valid values are "prod" or "dev". This determines the environment prefix used when storing events in S3.

- **`event_bucket`** (string, default: "nacc-event-logs"): S3 bucket name where submission events will be stored. The gear must have write access to this bucket.

Note: Event logging only occurs when processing files in the `nacc` direction with QC logging enabled (i.e., when a `form_configs_file` input is provided). If these conditions are not met, the event logging configuration parameters are ignored.

## Input

The input is a single CSV file, which must have columns `adcid` and `ptid`.

## Output

The gear has two output files.

- A CSV file consisting of the rows of the input file for which a NACCID was found, with an additional `naccid` column if the direction is `nacc` or additional `adcid` and `ptid` columns if the direction is `center`
  - Unless the configuration value `preserve_case` is set to `True`, all header keys will also be forced to lower case and spaces replaced with `_`
- A CSV file indicating errors, and specifically information about rows for which a NACCID was not found.
  The format of this file is determined by the FW interface for displaying errors.

Note: Event logging, when enabled, does not produce additional output files. Events are logged directly to the configured S3 bucket and do not affect the standard CSV output files described above.



