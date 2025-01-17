# Form Screening Gear

Prescreens input files to queue for [form-scheduler](../form_scheduler/index.md) gear. Checks to see if a file's basename suffix matches any of the accepted modules (case-insensitive), and adds queue tags to it. If it does not, reports an error. Otherwise, it then checks if a scheduler gear is pending/running and triggers one if not.

## Inputs

This gear takes two input files:

1. The input file (typically expected to be a CSV but not required) to verify
2. The scheduler gear config file - an example can be found in [gear/form_screening/data/form-scheduler-configs.json](../../gear/form_screening/data/form-scheduler-configs.json)

The gear also takes the following optional input parameters:

| Parameter | Required? | Default | Description |
| --------- | --------- | ------- | ----------- |
| `accepted_modules` | No | `"ENROLL,UDS,FTLD,LBD"` | Comma-deliminated list of accepted modules. Cannot be empty. |
| `queue_tags` | No | `"queued"` | Comma-deliminated list of tags to add to the prescreened file. Cannot be empty. |
| `dry_run` | No | `false` | Whether or not to do a dry run - will verify the file but will not add tags nor trigger a scheduler gear |

The gear does not have any explicit outputs but will add the tags specified in `tags_to_add` to the input file and trigger the schedule gear if it is not currently pending/running.
