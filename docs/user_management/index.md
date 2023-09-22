# User management

The user management utility reads a user file from the admin project and updates the listed users.

## Environment

The script expects the `FW_API_KEY` environment variables to be set, which should be an API key for the FW instance.

## Flywheel configuration

The script also expects there is an admin group with a project named `project-admin` that contains a YAML file given as an argument.
This file should contain a list of user information

```yaml
- authorizations:
    approve_data: <Boolean>
    audit_data: <Boolean>
    submit:
    - <datatype name>
    view_reports: <Boolean>
  center_id: <integer ID>
  credentials:
    id: <id-value>
    type: <type-name>
  email: <email-address>
  name:
    first_name: <user first name>
    last_name: <user last name>
  org_name: <center name>
  submit_time: <datetime of submission>
  ```

  Users are matched against groups with a tag matching `adcid-\d+` where `center_id` matches the digits.

  ## Running from command-line

  The script can be run with

  ```bash
  pants run user_management/src/python/user_app:bin -- <filename>
  ```

  which will update users listed in the named file.

  Additional command line arguments are `--dry_run` to run the script without making changes, and `--admin_group` to indicate the group in which the file is found.
  The default admin group is `nacc`.
  
  