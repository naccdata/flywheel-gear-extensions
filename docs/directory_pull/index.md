# NACC Directory Pull

This utility pulls user information from a Flywheel-access report in the NACC REDCap instance,
and then creates a file with the user information in a form that can be loaded by the user management utility.

## Environment

The script expects the following environment variables to be set:

1. `FW_API_KEY` an API key for the FW instance
2. `NACC_DIRECTORY_URL` the URL for the REDCap instance
3. `NACC_DIRECTORY_TOKEN` the API token for the NACC Directory project
4. `USER_REPORT_ID` the report ID for the user access report

## REDCap configuration

The script expects that there is a user access report that is defined in the directory project.

The following are assumed to be columns in the report

- `flywheel_access_information_complete` - integer indicating whether all information has been provided.
- `flywheel_access_activities` - list of activities indicated by letters `a` through `e`
- `fw_credential_type` - string indicating type of credential
- `fw_credential_id` - string ID for user credentials
- `firstname` - user first name
- `lastname` - user last name
- `contact_company_name` - the name of the center
- `adresearchctr` - string with numeric ID for center
- `email` - user email
- `fw_cred_sub_time` - submission time for credentials

## Running from command-line

The script can be run with

```bash
pants run directory_pull/src/python/directory_app/run.py -- --no-gear <output-file-path>
```

which will pull the current user access report from the REDCap instance and write YAML text to the given file.

If run with `--gear`, the script will read the remaining arguments from the Gear context, and will write the file to the `project-admin` project of the admin group (default is `nacc`).

The admin group may be given with `--admin_group`.

To do a dry run, use `--dry_run`

If run with `--gear`, the file will be uploaded to the `project-admin` project of the admin group.
The file path will be used as the file name.
