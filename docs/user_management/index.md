# User management

The user management utility reads user information from the user directory file and authorizations file, and for each user may

1. register the user in the CoManage registry, and email instructions to claim the registry record;
2. if the user registry record is claimed
   1. add the user to Flywheel,
   2. add authorized users to REDCap projects, and
   3. add user roles (from authorization file) to Flywheel projects.
3. remind the user if their record has not been claimed

For more on the user enrollment process see the [process documentation](https://github.com/naccdata/flywheel-gear-extensions/blob/main/docs/user_management/process.md)

## Environment

The gear should be run in an environment with environment variables `AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, and `AWS_DEFAULT_REGION` set.
These are used to access parameters in the AWS parameter store.

Parameters must be set for 

- CoManage API calls, and
- sender address for sending email notifications.

The gear also sends emails using AWS SES templating and needs templates for
 
- claiming registry record
- reminder for claiming registry record, and
- user creation. 

## Flywheel configuration

The script expects two YAML files as input: the list of users, and the map from user authorizations to Flywheel role names.

The user file should contain a list of user information

```yaml
---
- active: <Boolean>         # whether the user is active at a center
  adcid: <integer ID>       # the ADCID for the center
  auth_email: <email-address> # email address for authentication (registry)
  authorizations:           
    approve_data: <Boolean> # whether user can approve data
    audit_data: <Boolean>   # whether user audits data quality
    study_id: <study ID>    # string ID for study
    submit:
    - <datatype name>       # datatypes which user can submit
    view_reports: <Boolean> # whether user can view reports
  email: <email-address>    # user email
  name:
    first_name: <user first name> 
    last_name: <user last name>
  org_name: <center name>
```

The fields `active`, `name`, `email` and `auth_email` are required.
The `auth_email` field may be `null`.
The remaining fields can only be given if `active` is `true`.

The `email` field indicates the user's primary email address, while `auth_email` is the email address either through an InCommon identity provider or ORCiD.

The authorization map defines a mapping $project\to (authorization\to role)$

```yaml
---
<project-id>:
  approve-data: <rolename>
  audit-data: <rolename>
  view-reports: <rolename>
  submit-form: <rolename>
  submit-image: <rolename>
```

Valid project IDs are determined by the project management script.
These are:

- `accepted` or `accepted-<study-id>`
- `metadata`
- `ingest-<datatype>` or `ingest-<datatype>-<study-id>`
- `sandbox-<datatype>` or `sandbox-<datatype>-<study-id>`

The datatypes and study IDs are determined by the study definition used by project management.

The role names are set in the Flywheel instance.
Roles used by NACC for center users include `read-only`, `curate` and `upload`.

If an authorization has no access to a project, it should be left off the list.
For instance, `submit-form` would have no corresponding role for `ingest-dicom`

## Notification configuration

The gear manifest config includes a `notification_mode` parameter which affects how follow-up messages are sent.
Allowable values are

- `none` - don't send any follow up messages
- `date` - send a follow up at 7 day intervals up to 3 times
- `force` - send all follow up messages
