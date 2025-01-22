# Legacy Sanity Check

Runs sanity checks on legacy ingest projects, namely for a given input retrospective form:

1. Checks that there are not multiple IVP packets across ingest and retrospective projects and modules, except for the case of a single I packet in UDSv3 and a single I4 packet in UDSv4 for the UDS module
2. Checks that there are no duplicate records across UDSv3 and UDSv4 projects (matching on packet, visit number, and visit date)

If any errors are found, it emails the targets specified in `target_emails`

## Inputs

The gear takes two input files as input:

| Input File | Description |
| ---------- | ----------- |
| `input_file` | The input retrospective form to run the sanity checks against. The subject to evaluate will be pulled from this file and run against all modules. |
| `form_configs_file` | JSON file with the forms module configurations. Should be the same as the one used by the ingest project, e.g. `form-ingest-configs.json` |

and the following configuration values:

| Configuration Value | Default | Description |
| ------------------- | ------- | ----------- |
| `ingest_project_label` | `ingest-form` | The corresponding ingest project for this retrospective project; assumes there is one, throws an error if no corresponding ingest project is found |
| `sender_email` | `no-reply@naccdata.org` | Email to send error reports from |
| `target_emails` | `nacchelp@uw.edu` | Comma-deliminated list of target emails to send error reports to |
| `apikey_path_prefix` | `/prod/flywheel/gearbot` | The parameter store API-key path prefix for the gearbot |
