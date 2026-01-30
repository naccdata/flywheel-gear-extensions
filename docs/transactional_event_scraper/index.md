# Transactional Event Scraper

Scrapes existing QC status log files from a Flywheel project to generate historical submission and pass-qc events. This gear is designed to backfill event data for visits that were processed before event capture was implemented.

## Purpose

The transactional event scraper reconstructs the event history for form submissions by analyzing QC status log files that were created during the form processing pipeline. This allows NACC to:

- Build a complete historical record of form submissions and QC outcomes
- Populate the event system with data from visits processed before event capture was enabled
- Ensure consistency between QC status logs and the event tracking system

## How It Works

1. **Discovery**: Scans the project for all QC status log files (files with names matching `*-qc-status-log.json`)
2. **Filtering**: Optionally filters files by creation date using `start_date` and `end_date` parameters
3. **Extraction**: Reads each log file and extracts visit metadata (PTID, visit date, module, etc.) and QC status information
4. **Event Generation**: Creates two types of events for each log file:
   - **submit**: Records when the form data was submitted to the system
   - **pass-qc**: Records when the form passed all QC checks (only if QC status is "pass")
5. **Capture**: Stores events in the configured S3 bucket with appropriate environment prefixes

## Event Types Generated

### Submit Events

Created for every valid QC status log file found. These events record the initial submission of form data.

**Event structure**:

- Event type: `submit`
- Visit metadata: PTID, visit date, module, visit number, packet
- Timestamp: Derived from the log file's creation date
- Source: `transactional-event-scraper`

### Pass-QC Events

Created only for log files where the QC status is "pass". These events record successful completion of QC validation.

**Event structure**:

- Event type: `pass-qc`
- Visit metadata: PTID, visit date, module, visit number, packet
- Timestamp: Derived from the log file's creation date
- Source: `transactional-event-scraper`

## Configuration

This gear takes the following configuration parameters:

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `dry_run` | `false` | Whether to perform a dry run without capturing events. When enabled, the gear will process files and log what would be done, but will not write events to S3. |
| `event_bucket` | `"submission-events"` | S3 bucket name for event storage. The gear must have write access to this bucket. |
| `event_environment` | `"prod"` | Environment prefix for event storage. Valid values are "prod" or "dev". This determines the environment prefix used when storing events in S3. |
| `start_date` | (optional) | Start date for filtering files in YYYY-MM-DD format. Only files created on or after this date will be processed. |
| `end_date` | (optional) | End date for filtering files in YYYY-MM-DD format. Only files created on or before this date will be processed. |
| `apikey_path_prefix` | `"/prod/flywheel/gearbot"` | The instance-specific AWS parameter path prefix for API key. |

## Inputs

This gear requires only the Flywheel API key input:

| Input | Description |
| ----- | ----------- |
| `api-key` | Flywheel API key for accessing the project and its files. |

## Environment

This gear uses AWS S3 for event storage and the AWS SSM parameter store for API key retrieval. It expects that AWS credentials are available in environment variables within the Flywheel runtime:

- `AWS_SECRET_ACCESS_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_DEFAULT_REGION`

The gear needs to be added to the allow list for these variables to be shared.

## Running the Gear

### Standard Run

To scrape all QC status log files in a project:

1. Navigate to the project in Flywheel
2. Run the transactional-event-scraper gear
3. Use default configuration or adjust `event_bucket` and `event_environment` as needed

### Dry Run

To preview what would be processed without capturing events:

1. Set `dry_run` to `true`
2. Run the gear
3. Review the logs to see which files would be processed and what events would be generated

### Date-Filtered Run

To process only files within a specific date range:

1. Set `start_date` to the beginning of your desired range (e.g., "2024-01-01")
2. Set `end_date` to the end of your desired range (e.g., "2024-12-31")
3. Run the gear

This is useful for:

- Processing files in batches
- Reprocessing a specific time period
- Testing on a subset of data

## Output

The gear produces log output with processing statistics:

- **Files processed**: Number of log files successfully processed
- **Events captured**: Number of submit and pass-qc events created
- **Files skipped**: Number of files skipped (due to date filtering or extraction failures)
- **Errors encountered**: Number of files that failed to process

No output files are created. All events are captured directly to the configured S3 bucket.

## Use Cases

### Initial Backfill

When first enabling event capture, run this gear to populate historical events for all existing QC status logs:

```json
{
  "dry_run": false,
  "event_bucket": "submission-events",
  "event_environment": "prod"
}
```

### Incremental Updates

To add events for a specific time period (e.g., after fixing an issue):

```json
{
  "dry_run": false,
  "event_bucket": "submission-events",
  "event_environment": "prod",
  "start_date": "2024-06-01",
  "end_date": "2024-06-30"
}
```

### Testing

To test the scraper on development data:

```json
{
  "dry_run": true,
  "event_bucket": "submission-events-dev",
  "event_environment": "dev"
}
```

## Limitations

- Only processes files that match the QC status log naming pattern (`*-qc-status-log.json`)
- Requires that log files contain valid visit metadata (PTID, visit date, module)
- Event timestamps are based on log file creation dates, not the actual submission/QC completion times
- Does not process files that fail metadata extraction (these are logged and skipped)
- Individual file processing errors do not stop the overall scraping process

## Related Gears

- [Form Scheduler](../form_scheduler/index.md): Creates QC status log files and captures real-time events during form processing
- [Form QC Coordinator](../form_qc_coordinator/index.md): Coordinates QC checks and updates QC status logs
- [Identifier Lookup](../identifier_lookup/index.md): Captures submit events during identifier lookup for form submissions
