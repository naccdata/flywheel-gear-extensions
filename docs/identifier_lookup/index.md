# Identifier Lookup

The identifier-lookup gear reads participant IDs from a tabular (CSV) input file and performs identifier lookups in two directions:

- **NACC direction** (`direction: "nacc"`): Looks up NACCIDs from center identifiers (adcid + ptid)
- **Center direction** (`direction: "center"`): Looks up center identifiers (adcid + ptid) from NACCIDs

The gear outputs a CSV file with the looked-up identifiers appended. If any rows fail lookup, an error file is produced listing the failures.



## Environment

This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables within the Flywheel runtime.
The variables used are `AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`.
The gear needs to be added to the allow list for these variables to be shared.

## Configuration

Gear configs are defined in [manifest.json](../../gear/identifier_lookup/src/docker/manifest.json).

### Supported Scenarios

The gear supports three main usage scenarios:

#### Scenario 1: Single Center Form Submission (Default)

**Use case**: Process form data submissions from a single center with full validation and QC logging.

**Configuration**:

```json
{
  "direction": "nacc",
  "single_center": true,
  "module": "uds",
  "event_environment": "prod",
  "event_bucket": "nacc-event-logs"
}
```

**Inputs**:

- `input_file`: CSV file with `adcid` and `ptid` columns
- `form_configs_file`: JSON file with module configurations (required)

**Behavior**:

- All rows must have the same `adcid` matching the project's pipeline ADCID
- Center validation is enforced (validates ADCID matches and PTID format)
- Module-specific field validation is performed
- QC status logs are created
- Visit events are captured to S3 (if event capture is configured)
- Output includes `naccid` and `module` columns

**Event Capture**:

When event capture is configured (by providing `event_environment` and `event_bucket`), the gear will create submission events for each valid visit row. These events are captured to an S3 bucket for tracking data submissions in the NACC event system.

Event capture behavior:

- Creates a submit event for each valid visit row in the CSV
- Events include visit metadata such as center, project, visit date, and packet information
- Event capture failures do not affect the primary identifier lookup functionality
- Events are stored in the configured S3 bucket with environment-specific prefixes

Event capture configuration parameters:

- **`event_environment`** (string, required for event capture): Environment for event capture. Valid values are "prod" or "dev". This determines the environment prefix used when storing events in S3.
- **`event_bucket`** (string, required for event capture): S3 bucket name where submission events will be stored. The gear must have write access to this bucket.

**When to use**: Standard form data processing pipelines where data comes from a single center.

#### Scenario 2: Multi-Center Identifier Lookup

**Use case**: Look up NACCIDs for data from multiple centers without center-specific validation.

**Configuration**:

```json
{
  "direction": "nacc",
  "single_center": false
}
```

**Inputs**:

- `input_file`: CSV file with `adcid` and `ptid` columns (can have different ADCIDs per row)
- `form_configs_file`: Optional - if provided, enables field validation without center validation

**Behavior**:

- Rows can have different `adcid` values
- No center validation is performed
- If `form_configs_file` is provided, module field validation is still performed
- Output includes `naccid` column (and `module` if configs provided)

**When to use**: Processing aggregated data from multiple centers, or when you need identifier lookup without strict center validation.

#### Scenario 3: Reverse Lookup (NACCID to Center IDs)

**Use case**: Look up center identifiers from NACCIDs.

**Configuration**:

```json
{
  "direction": "center"
}
```

**Inputs**:

- `input_file`: CSV file with `naccid` column

**Behavior**:

- Looks up `adcid` and `ptid` for each `naccid`
- No validation or QC logging is performed
- Output includes `adcid` and `ptid` columns

**When to use**: When you have NACCIDs and need to determine which center and participant they correspond to.

### Configuration Parameters

- **`direction`** (string, default: "nacc"): Direction of identifier mapping
  - `"nacc"`: Look up NACCIDs from center identifiers (adcid + ptid)
  - `"center"`: Look up center identifiers from NACCIDs

- **`single_center`** (boolean, default: true): Whether to enforce single-center validation
  - `true`: All rows must have the same `adcid` matching the project's pipeline ADCID (only applies when `form_configs_file` is provided)
  - `false`: Allows rows with different `adcid` values, disables center validation

- **`module`** (string, optional): Module name for form processing (e.g., "uds", "lbd")
  - Can be inferred from filename suffix (e.g., `data-uds.csv` → module "UDS")
  - If both filename suffix and config specify module, they must match
  - Required when using `form_configs_file` unless filename has module suffix

- **`preserve_case`** (boolean, default: true): Whether to preserve the case of header keys in the input file

- **`database_mode`** (string, default: "prod"): Whether to lookup identifiers from "dev" or "prod" database

## Input

The input is a single CSV file, which must have columns `adcid` and `ptid`.

## Output

The gear has two output files.

- A CSV file consisting of the rows of the input file for which a NACCID was found, with an additional `naccid` column if the direction is `nacc` or additional `adcid` and `ptid` columns if the direction is `center`
  - Unless the configuration value `preserve_case` is set to `True`, all header keys will also be forced to lower case and spaces replaced with `_`
- A CSV file indicating errors, and specifically information about rows for which a NACCID was not found.
  The format of this file is determined by the FW interface for displaying errors.

Note: Event capture, when enabled, does not produce additional output files. Events are captured directly to the configured S3 bucket and do not affect the standard CSV output files described above.



