# Form Scheduler

Queues project files for the submission pipeline and captures outcome events (pass-qc, not-pass-qc) after pipeline completion. Intended to be triggered by the [form-screening](../form_sreening/index.md) gear.

## Event Capture

The form-scheduler captures outcome events after pipeline completion:

- **pass-qc**: Visit successfully completed all QC checks
- **not-pass-qc**: Visit failed QC validation

Submit events are handled separately by the identifier-lookup gear. For detailed event capture documentation, see the [gear-specific event logging guide](../../gear/form_scheduler/docs/event-logging.md).

## Logic

1. Pulls the current list of project files with the specified queue tags and adds them to processing queues for each module sorted by file timestamp
2. Process the queues in a round robin
    1. Check whether there are any submission pipelines running/pending; if so, wait for it to finish
    2. Pull the next CSV from the queue and remove the queue tags
    3. Trigger the submission pipeline
    4. Wait for the triggered submission pipeline to finish
    5. Send email to user that the submission pipeline is complete
    6. Move to next queue
3. Repeat 2) until all queues are empty
4. Repeat from the beginning until there are no more files to be queued

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
