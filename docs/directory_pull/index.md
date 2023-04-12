# NACC Directory Pull

This utility pulls user information from a Flywheel-access report in the NACC REDCap instance,
and then creates a file with the user information in a form that can be loaded by the user management utility.

## Running from command-line

The script expects the following environment variables to be set:
1. `FW_API_KEY` an API key for the FW instance
2. `NACC_DIRECTORY_URL` the URL for the REDCap instance
3. `NACC_DIRECTORY_TOKEN` the API token for the NACC Directory project
4. `USER_REPORT_ID` the report ID for the user access report

The script can be run with

```bash
./pants run directory_pull/src/python/run.py -- <output-file-path>
```

which will pull the current user access report from the REDCap instance and write YAML text to the given file.

If run with `--gear`, the script will read the remaining arguments from the Gear context, and will write the file to the `project-admin` project of the admin group (default is `nacc`).

The admin group may be given with `--admin_group`.

To do a dry run, use `--dry_run`

