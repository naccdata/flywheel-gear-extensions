# Form Scheduler

Queues project files for the submission pipeline. Intended to be triggered by the [form-screening](../form_sreening/index.md) gear.

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

## Inputs

This gear takes the following optional input parameters:

| Parameter | Required? | Default | Description |
| --------- | --------- | ------- | ----------- |
| `submission_pipeline` | No | `file-validator,identifier-lookup,form-transformer,form-qc-coordinator,form-qc-checker` | Comma-deliminated list of gears representing a submission pipeline. The first one must be `file-validator` |
| `accepted_modules` | No | `"UDS,ENROLL,FTLD,LBD"` | Comma-deliminated list of accepted modules, listed in order of priority. There will be one queue for each. Cannot be empty. |
| `queue_tags` | No | `"queued"` | Comma-deliminated list of tags to add to the prescreened file. Cannot be empty. |
| `source_email` | No | `""` | Source email address to send emails from. If empty will not send emails. |

This gear currently does not support a `dry-run` mode.
