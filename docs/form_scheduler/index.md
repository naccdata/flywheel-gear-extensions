# Form Scheduler

This gear manages the coordination between the different pipelines and captures outcome events after a pipeline completion. Currently supports deletion, submission, and finalization pipelines. Intended to be triggered by the [form-screening](../form_sreening/index.md) gear.

## Pipeline types and processing order

The scheduler manages three pipeline types, processed in the following fixed order each run:

| Order | Pipeline | Queue tag | File type | Starting gear |
|-------|----------|-----------|-----------|---------------|
| 1st | deletion | `pending-delete` | `.json` | form-deletion |
| 2nd | submission | `queued` | `.csv` | nacc-file-validator |
| 3rd | finalization | `submission-completed` | `.json` | form-qc-coordinator |

Each pipeline runs to completion before the next one starts.

### Module ordering

Within each pipeline, modules are processed in round-robin order. Order of the modules for each pipeline is specified in the pipeline configurations file. The position of the UDS module in that order is intentional:

- **Submission and finalization** — UDS is listed first (`UDS, FTLD, LBD, MLST, BDS, CLS, NP`). This ensures UDS records are prioritized at the start of each cycle, as other modules may depend on UDS data being present.
- **Deletion** — UDS is listed last (`FTLD, LBD, MLST, BDS, CLS, NP, UDS`). This ensures dependent module records are deleted before the foundational UDS record is removed.

### Sequential vs. subject-parallel processing

Pipelines differ in how files are dispatched within each module queue:

- **Submission (sequential)**: one file is triggered at a time. The scheduler waits for the full pipeline to complete before triggering the next file.
- **Deletion and finalization (subject-parallel)**: files are grouped by subject. Each processing round triggers one file per subject as a batch — all batch jobs are dispatched before waiting — then the scheduler waits for the entire batch to finish before starting the next round.
  
## Event Capture

The form-scheduler captures outcome events after a pipeline completes:
- **pass-qc**: Visit successfully completed all QC checks
- **delete**: Delete requests that are successfully completed

Submit events are handled separately by the identifier-lookup gear. For detailed event capture documentation, see the [gear-specific event logging guide](../../gear/form_scheduler/docs/event-logging.md).

## Configuration

This gear takes the following configuration parameters:

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `source_email` | `"nacchelp@uw.edu"` | Source email address to send completion notifications from. If empty, emails will not be sent. |
| `portal_url_path` | `"/prod/flywheel/portal"` | Parameter path for the portal URL used in email notifications. |
| `apikey_path_prefix` | `"/prod/flywheel/gearbot"` | The instance-specific AWS parameter path prefix for API key. |
| `event_bucket` | `"submission-events"` | S3 bucket name for visit event capture. The gear must have write access to this bucket. |
| `event_environment` | `"prod"` | Environment for event capture. Valid values are "prod" or "dev". This determines the environment prefix used when storing events in S3. |

## Inputs

This gear requires the following input files:

| Input | Description |
| ----- | ----------- |
| `pipeline_configs_file` | A JSON file with pipeline configurations defining the submission pipeline stages and their settings. |
| `form_configs_file` | A JSON file with form module configurations for validation and processing. |

This gear currently does not support a `dry-run` mode.
