# Event Log Format Specification

## Overview

This document specifies the format and structure of visit events logged to S3 by the NACC event logging system. This specification is intended for systems that consume these event logs, such as checkpoint processes or analytics pipelines.

**Note**: This specification covers events from both identifier-lookup (submit events) and form-scheduler (outcome events) gears.

## S3 Storage Structure

### Bucket Organization

Events are stored in S3 with a flat structure organized by environment:

```
s3://{bucket-name}/
├── prod/
│   ├── log-submit-20240115-100000-42-ingest-form-110001-01.json
│   ├── log-pass-qc-20240115-102000-42-ingest-form-110001-01.json
│   ├── log-submit-20240115-100000-44-ingest-form-dvcid-110003-01.json
│   └── log-not-pass-qc-20240116-143000-45-ingest-dicom-leads-220002-02.json
└── dev/
    ├── log-submit-20240115-100000-42-ingest-form-110001-01.json
    └── ...
```

### Path Components

- **bucket-name**: S3 bucket configured for event logging
- **environment**: Environment prefix (`prod` or `dev`)

### Filename Components

Filenames encode key event metadata for efficient filtering without reading file contents:

```
log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
```

- **action**: Event type (`submit`, `pass-qc`, `not-pass-qc`, `delete`)
- **timestamp**: Event timestamp in format `YYYYMMDD-HHMMSS`
- **adcid**: Pipeline ADCID (integer)
- **project**: Project label (sanitized, special characters replaced with hyphens)
- **ptid**: Participant ID
- **visitnum**: Visit number

### Example Paths

For events with:
- environment: `prod`
- pipeline_adcid: `42`
- project_label: `ingest-form` (ADRC study, no suffix)
- ptid: `110001`
- visit_number: `01`
- submit timestamp: `2024-01-15T10:00:00Z`
- pass-qc timestamp: `2024-01-15T10:20:00Z`

Events are stored at:
```
s3://nacc-events/prod/log-submit-20240115-100000-42-ingest-form-110001-01.json
s3://nacc-events/prod/log-pass-qc-20240115-102000-42-ingest-form-110001-01.json
```

For non-ADRC studies:
```
s3://nacc-events/prod/log-submit-20240115-100000-44-ingest-form-dvcid-110003-01.json
s3://nacc-events/prod/log-submit-20240116-100000-45-ingest-dicom-leads-220002-02.json
```

## Event File Format

### File Naming Convention

Event files follow this naming pattern:
```
log-{action}-{YYYYMMDD-HHMMSS}-{adcid}-{project}-{ptid}-{visitnum}.json
```

Where:
- **action**: Event type (`submit`, `pass-qc`, `not-pass-qc`, `delete`)
- **YYYYMMDD-HHMMSS**: Event timestamp in format `YYYYMMDD-HHMMSS`
  - Example: `20240115-100000` for `2024-01-15T10:00:00Z`
  - Derived from the event's `timestamp` field
  - Note: This is when the action occurred, not when the event was logged
- **adcid**: Pipeline ADCID (integer)
- **project**: Project label (sanitized)
- **ptid**: Participant ID
- **visitnum**: Visit number

### Collision Avoidance

The filename components provide natural uniqueness:
- **timestamp**: Precise to the second
- **adcid + project**: Identifies the pipeline
- **ptid + visitnum**: Identifies the visit

In the extremely unlikely event of a collision (same visit, same action, same second), the last write wins. This is acceptable since events are idempotent.

### File Content

Each event file contains a single JSON object representing one visit event.

## Event Schema

### VisitEvent Object

```json
{
  "action": "string",
  "study": "string",
  "pipeline_adcid": "integer",
  "project_label": "string",
  "center_label": "string",
  "gear_name": "string",
  "ptid": "string",
  "visit_date": "string (ISO date)",
  "visit_number": "string",
  "datatype": "string",
  "module": "string",
  "packet": "string | null",
  "timestamp": "string (ISO datetime)"
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | Event type: `"submit"`, `"pass-qc"`, `"not-pass-qc"`, `"delete"` |
| `study` | string | Yes | Study identifier (e.g., `"adrc"`, `"dvcid"`, `"leads"`), defaults to `"adrc"` |
| `pipeline_adcid` | integer | Yes | ADCID identifying the pipeline/center |
| `project_label` | string | Yes | Flywheel project label following convention: `"ingest-{datatype}-{study}"` for non-ADRC studies, `"ingest-{datatype}"` for ADRC (e.g., `"ingest-form"`, `"ingest-form-dvcid"`, `"ingest-dicom-leads"`) |
| `center_label` | string | Yes | Center/group label |
| `gear_name` | string | Yes | Name of gear that logged the event (e.g., `"form-scheduler"`) |
| `ptid` | string | Yes | Participant ID (max 10 characters, matches pattern `^[A-Z0-9]+$`) |
| `visit_date` | string | Yes | Visit date in ISO format `YYYY-MM-DD` |
| `visit_number` | string | Yes | Visit number (e.g., `"01"`, `"02"`) |
| `datatype` | string | Yes | Data type: `"form"`, `"dicom"`, etc. |
| `module` | string | No | Module name for forms: `"UDS"`, `"FTLD"`, `"LBD"`, etc. (required when datatype=`"form"`) |
| `packet` | string or null | No | Packet type: `"I"`, `"F"`, etc. (may be null) |
| `timestamp` | string | Yes | ISO 8601 datetime when the action occurred (UTC) |

### Field Constraints

#### action
- Enum: `"submit"`, `"pass-qc"`, `"not-pass-qc"`, `"delete"`
- Case-sensitive

#### study
- Study identifier string
- Common values: `"adrc"`, `"dvcid"`, `"leads"`
- Lowercase
- Defaults to `"adrc"`
- Corresponds to project label suffix (except for ADRC which has no suffix)
- Note: Not to be confused with module names (e.g., LBD, FTLD are modules, not studies)

#### project_label
- Format: `"ingest-{datatype}-{study}"` for non-ADRC studies
- Format: `"ingest-{datatype}"` for ADRC study (no suffix)
- Examples:
  - ADRC forms: `"ingest-form"`
  - DVCID forms: `"ingest-form-dvcid"`
  - LEADS DICOM: `"ingest-dicom-leads"`

#### ptid
- Pattern: `^[A-Z0-9]+$`
- Max length: 10 characters
- Example: `"110001"`, `"ABC123"`

#### visit_date
- Format: `YYYY-MM-DD` (ISO 8601 date)
- Example: `"2024-01-15"`

#### visit_number
- String representation of visit number
- Examples: `"01"`, `"02"`, `"10"`
- May include leading zeros

#### datatype
- Common values: `"form"`, `"dicom"`
- Lowercase

#### module
- Required when `datatype="form"`
- Common values: `"UDS"`, `"FTLD"`, `"LBD"`, `"FTLD-NP"`, `"FTLD-B"`
- Uppercase

#### timestamp
- Format: ISO 8601 datetime with timezone
- Example: `"2024-01-15T10:00:00Z"`, `"2024-01-15T10:00:00-05:00"`
- Represents when the action occurred (not when event was logged)

## Event Types and Semantics

### submit

Indicates a visit was submitted for processing.

**Note**: Submit events are handled by identifier-lookup gear, not form-scheduler.

**Timestamp**: When the file was uploaded to Flywheel

**Example (ADRC study)**:
```json
{
  "action": "submit",
  "study": "adrc",
  "pipeline_adcid": 42,
  "project_label": "ingest-form",
  "center_label": "alpha",
  "gear_name": "form-scheduler",
  "ptid": "110001",
  "visit_date": "2024-01-15",
  "visit_number": "01",
  "datatype": "form",
  "module": "UDS",
  "packet": "I",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Example (DVCID study with LBD module)**:
```json
{
  "action": "submit",
  "study": "dvcid",
  "pipeline_adcid": 44,
  "project_label": "ingest-form-dvcid",
  "center_label": "beta",
  "gear_name": "form-scheduler",
  "ptid": "110003",
  "visit_date": "2024-01-15",
  "visit_number": "01",
  "datatype": "form",
  "module": "LBD",
  "packet": "I",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Example (LEADS study with DICOM)**:
```json
{
  "action": "submit",
  "study": "leads",
  "pipeline_adcid": 45,
  "project_label": "ingest-dicom-leads",
  "center_label": "gamma",
  "gear_name": "dicom-scheduler",
  "ptid": "220002",
  "visit_date": "2024-01-16",
  "visit_number": "02",
  "datatype": "dicom",
  "timestamp": "2024-01-16T14:30:00Z"
}
```

### pass-qc

Indicates a visit successfully passed all QC checks.

**Timestamp**: When the pipeline completed successfully

**Requirements for this event**:
1. JSON file exists at ACQUISITION level (form-transformer succeeded)
2. ALL pipeline gears have status="PASS" in QC metadata

**Example**:
```json
{
  "action": "pass-qc",
  "study": "adrc",
  "pipeline_adcid": 42,
  "project_label": "ingest-form",
  "center_label": "alpha",
  "gear_name": "form-scheduler",
  "ptid": "110001",
  "visit_date": "2024-01-15",
  "visit_number": "01",
  "datatype": "form",
  "module": "UDS",
  "packet": "I",
  "timestamp": "2024-01-15T10:20:00Z"
}
```

### not-pass-qc

Indicates a visit failed QC validation.

**Timestamp**: When the pipeline failed or completed with errors

**Reasons for this event**:
- No JSON file at ACQUISITION level (early pipeline failure)
- Any gear has status != "PASS" in QC metadata
- Validation errors found

**Example**:
```json
{
  "action": "not-pass-qc",
  "study": "adrc",
  "pipeline_adcid": 42,
  "project_label": "ingest-form",
  "center_label": "alpha",
  "gear_name": "form-scheduler",
  "ptid": "110001",
  "visit_date": "2024-01-15",
  "visit_number": "01",
  "datatype": "form",
  "module": "UDS",
  "packet": "I",
  "timestamp": "2024-01-15T10:08:00Z"
}
```

### delete

Indicates a visit was deleted from the system.

**Note**: Currently not implemented by form-scheduler, but reserved for future use.

## Event Patterns and Sequences

### Typical Successful Submission

For a new visit that passes QC immediately:

1. **submit** event (timestamp = upload time) - *logged by identifier-lookup gear*
2. **pass-qc** event (timestamp = completion time) - *logged by form-scheduler gear*

Events logged by different gears at different times.

### Typical Failed Submission

For a new visit that fails QC:

1. **submit** event (timestamp = upload time) - *logged by identifier-lookup gear*
2. **not-pass-qc** event (timestamp = failure time) - *logged by form-scheduler gear*

Events logged by different gears at different times.

### Re-evaluation After Dependency Resolution

For a visit that was blocked on a dependency (e.g., UDS packet) and later re-evaluated:

**Initial submission** (UDS packet not yet cleared):
- **submit** event logged by identifier-lookup gear
- No outcome events (visit blocked, not processed by form-scheduler)

**After dependency cleared** (separate form-scheduler job):
1. **pass-qc** event (timestamp = completion time) - *logged by form-scheduler gear*

Only the outcome event is logged by form-scheduler; the submit event was already logged by identifier-lookup when first uploaded.

### Deferred QC Approval

For a visit with QC alerts that are later approved:

**Initial submission**:
1. **submit** event (timestamp = upload time) - *logged by identifier-lookup gear*
2. **not-pass-qc** event (timestamp = completion time with alerts) - *logged by form-scheduler gear*

**After approval** (separate form-scheduler job):
1. **pass-qc** event (timestamp = approval time) - *logged by form-scheduler gear*

## Important Considerations for Consumers

### Event Ordering

- Events are not guaranteed to be in chronological order in S3
- Use the `timestamp` field to determine actual event sequence
- Multiple events for the same visit may be logged at different times

### Event Uniqueness

- A visit may have multiple events of the same type over time
- Example: `not-pass-qc` followed by `pass-qc` after corrections
- Consumers should track the most recent event per visit

### Missing Events

- Not all visits will have both `submit` and outcome events in the same job
- Re-evaluated visits may only have outcome events
- Early pipeline failures may not generate events (no JSON file = no visit metadata)

### Timestamp Interpretation

- `timestamp` reflects when the action occurred, not when the event was logged
- `submit` events use upload timestamp (from file creation time)
- Outcome events use completion timestamp (when pipeline finished)
- Events may be logged minutes or hours after the timestamp

### File Naming and Timestamps

- Event files are named using the event `timestamp`, not the `visit_date`
- The filename timestamp format is `YYYYMMDD-HHMMSS` (e.g., `20240115-100000`)
- Multiple events for the same visit will have different timestamps in their filenames
- Each event file has a unique filename based on action, timestamp, and visit identifiers
- Filenames are self-documenting and contain key metadata for filtering

## S3 Access Patterns

The flat structure enables efficient querying using glob patterns and filename parsing.

### Listing All Events

To get all events in an environment:
```
s3://{bucket}/prod/log-*.json
```

This requires only a single S3 LIST operation.

### Listing Events by Action Type

To find all events of a specific type (e.g., all pass-qc events):
```
s3://{bucket}/prod/log-pass-qc-*.json
```

Examples:
- All submit events: `log-submit-*.json`
- All QC failures: `log-not-pass-qc-*.json`

### Listing Events by Date Range

To find all events that occurred on a specific date:
```
s3://{bucket}/prod/log-*-{YYYYMMDD}-*.json
```

Examples:
- All events on January 15, 2024: `log-*-20240115-*.json`
- All events in January 2024: `log-*-202401*.json`

### Listing Events by ADCID

To find all events for a specific ADCID:
```
s3://{bucket}/prod/log-*-*-{adcid}-*.json
```

Example: All events for ADCID 42:
```
s3://{bucket}/prod/log-*-*-42-*.json
```

### Listing Events by Project

To find all events for a specific project:
```
s3://{bucket}/prod/log-*-*-*-{project}-*.json
```

Example: All events for ingest-form (ADRC):
```
s3://{bucket}/prod/log-*-*-*-ingest-form-*.json
```

Example: All events for specific study projects:
```
s3://{bucket}/prod/log-*-*-*-ingest-form-dvcid-*.json
s3://{bucket}/prod/log-*-*-*-ingest-dicom-leads-*.json
```

### Listing Events by Participant

To find all events for a specific participant:
```
s3://{bucket}/prod/log-*-*-*-*-{ptid}-*.json
```

Example: All events for PTID 110001:
```
s3://{bucket}/prod/log-*-*-*-*-110001-*.json
```

### Listing Events by Visit

To find all events for a specific visit:
```
s3://{bucket}/prod/log-*-*-*-*-{ptid}-{visitnum}.json
```

Example: All events for PTID 110001, visit 01:
```
s3://{bucket}/prod/log-*-*-*-*-110001-01.json
```

### Chronological Processing

Files naturally sort chronologically by filename:
```python
# List and sort files
files = s3.list_objects(Prefix="prod/log-")
sorted_files = sorted(files, key=lambda x: x['Key'])

# Process in chronological order
for file in sorted_files:
    process_event(file)
```

### Incremental Processing

Track the last processed timestamp to efficiently process only new events:
```python
last_processed = "20240115-100000"
new_files = [f for f in files if extract_timestamp(f) > last_processed]
```

## Example: Complete Event Sequence

### Scenario: Successful UDS Visit Submission

**Visit Details**:
- PTID: `110001`
- Visit Date: `2024-01-15`
- Visit Number: `01`
- Module: `UDS`
- Packet: `I`
- ADCID: `42`
- Project: `ingest-form-alpha`

**Timeline**:
1. User uploads CSV at `2024-01-15T10:00:00Z`
2. Pipeline processes the visit
3. All QC checks pass
4. Pipeline completes at `2024-01-15T10:20:00Z`

**Events Logged**:

File: `s3://nacc-events/prod/log-submit-20240115-100000-42-ingest-form-110001-01.json`
```json
{
  "action": "submit",
  "study": "adrc",
  "pipeline_adcid": 42,
  "project_label": "ingest-form",
  "center_label": "alpha",
  "gear_name": "form-scheduler",
  "ptid": "110001",
  "visit_date": "2024-01-15",
  "visit_number": "01",
  "datatype": "form",
  "module": "UDS",
  "packet": "I",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

File: `s3://nacc-events/prod/log-pass-qc-20240115-102000-42-ingest-form-110001-01.json`
```json
{
  "action": "pass-qc",
  "study": "adrc",
  "pipeline_adcid": 42,
  "project_label": "ingest-form",
  "center_label": "alpha",
  "gear_name": "form-scheduler",
  "ptid": "110001",
  "visit_date": "2024-01-15",
  "visit_number": "01",
  "datatype": "form",
  "module": "UDS",
  "packet": "I",
  "timestamp": "2024-01-15T10:20:00Z"
}
```

## Validation

### JSON Schema

Consumers should validate event files against this JSON schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": [
    "action",
    "pipeline_adcid",
    "project_label",
    "center_label",
    "gear_name",
    "ptid",
    "visit_date",
    "visit_number",
    "datatype",
    "timestamp"
  ],
  "properties": {
    "action": {
      "type": "string",
      "enum": ["submit", "pass-qc", "not-pass-qc", "delete"]
    },
    "study": {
      "type": "string",
      "minLength": 1,
      "default": "adrc"
    },
    "pipeline_adcid": {
      "type": "integer",
      "minimum": 1
    },
    "project_label": {
      "type": "string",
      "minLength": 1
    },
    "center_label": {
      "type": "string",
      "minLength": 1
    },
    "gear_name": {
      "type": "string",
      "minLength": 1
    },
    "ptid": {
      "type": "string",
      "pattern": "^[A-Z0-9]+$",
      "maxLength": 10
    },
    "visit_date": {
      "type": "string",
      "format": "date"
    },
    "visit_number": {
      "type": "string",
      "minLength": 1
    },
    "datatype": {
      "type": "string",
      "minLength": 1
    },
    "module": {
      "type": ["string", "null"]
    },
    "packet": {
      "type": ["string", "null"]
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

## Design Rationale

### Why Flat Structure?

The flat structure was chosen to optimize for the primary use case: scraping all events into a single Parquet table.

**Advantages:**
1. **Simple listing**: Single S3 LIST operation gets all events
2. **No recursive traversal**: Eliminates complexity in consumer code
3. **Efficient filtering**: Glob patterns work directly on filenames
4. **Chronological ordering**: Natural sort by filename gives time order
5. **Self-documenting**: Key metadata visible in filename without reading file
6. **Atomic writes**: Single file write, no directory management

**Trade-offs:**
- Longer filenames (60-80 characters) vs. hierarchical paths
- No visual hierarchy in S3 console (but programmatic access is primary use case)
- All metadata duplicated in filename and file content (acceptable for event logs)

### Why Include Metadata in Filename?

Including key identifiers (action, timestamp, adcid, project, ptid, visitnum) in the filename enables:
1. **Filtering without reading files**: Glob patterns for efficient queries
2. **Debugging**: Identify events at a glance in logs or S3 console
3. **Collision avoidance**: Composite key provides natural uniqueness
4. **Incremental processing**: Track last processed timestamp from filename

### Environment Separation

The `prod/` and `dev/` prefixes provide:
1. **Clear separation**: Prevents accidental mixing of production and development data
2. **Independent testing**: Dev environment can be cleared without affecting production
3. **Simple configuration**: Single bucket with environment prefix

## Versioning

**Current Version**: 1.0

This specification may evolve over time. Future versions will:
- Maintain backward compatibility where possible
- Document breaking changes clearly
- Use semantic versioning

## Contact

For questions about this specification or the event logging system, contact the NACC Data Platform team.
