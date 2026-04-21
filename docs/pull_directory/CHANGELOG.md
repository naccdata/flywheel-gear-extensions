# Changelog

All notable changes to this gear are documented in this file.

## 4.1.0

* Adds optional `preceding_hours` configuration for incremental pulls of recently modified records
* When `preceding_hours` is set to a positive value, the gear computes a date range and passes it to the REDCap export API
* Defaults to 0 (full pull), maintaining backward compatibility with existing schedules
* Adds validation that `preceding_hours` is non-negative
* Adds logging to indicate whether the gear is performing a full pull or an incremental pull

## 4.0.3

* Fixes REDCap `export_records` field list to use base field names for checkbox fields, allowing REDCap to return expanded columns automatically

## 4.0.2

* Fixes handling of REDCap checkbox fields (`web_report_access`, `study_selections`, `affiliated_study`) for `export_records` format
* Maps expanded checkbox columns (`web_report_access___web`, `web_report_access___repdash`) directly to model fields instead of parsing comma-separated strings
* Removes unused `study_selections` and `affiliated_study` fields from `DirectoryAuthorizations` model

## 4.0.1

* Fixes missing CLARiTI role fields by switching from REDCap report-based retrieval to `export_records` with explicit field list derived from the directory authorization model
* Pre-filters exported records to retain only approved entries before processing

## 4.0.0

* Adds signed user agreement check to directory processing
* Rejects directory entries where the user has not signed the NACC user agreement
* Adds `MISSING_USER_AGREEMENT` error event category for unsigned agreement tracking
* Adds `signed_user_agreement` field to `DirectoryAuthorizations` model
* Updates `convert_flag_string` validator to handle numeric string values beyond "1"
* Refactors directory test fixtures to use shared `create_directory_entry` helper

## 3.1.1

* Reclassifies `cl_ror_access_level` field as participant-summary datatype resource instead of dashboard resource
* Renames `clariti_dashboard_ror_access_level` to `clariti_datatype_participant_summary_access_level` to reflect correct resource type
* Adds 'participant-summary' to supported datatype names
* Adds name whitespace stripping to `DirectoryAuthorizations` field validator to handle REDCap data with trailing spaces
* Improves data normalization to prevent name matching issues in COManage registry and Flywheel

## 3.1.0

* Adds support for CLARiTI role-based authorization mapping
* Adds parsing of 14 CLARiTI organizational role fields from REDCap directory report
* Adds parsing of CLARiTI admin core member role field
* Maps CLARiTI payment roles to payment-tracker dashboard view access
* Maps CLARiTI organizational roles to enrollment dashboard view access
* Maps CLARiTI admin core member role to both payment-tracker and enrollment dashboard access
* Creates study authorizations with `study_id="clariti"` for users with CLARiTI roles
* Maintains backward compatibility - REDCap reports without CLARiTI fields continue to work

## 3.0.1

* Fixes validation error when processing directory entries with empty or 'NA' adcid values
* Updates `DirectoryAuthorizations.convert_adcid` validator to run in `mode="before"` to handle string conversion before Pydantic type checking
* Handles empty strings, whitespace-only strings, and 'NA' values by converting them to None

## 3.0.0

* Refactors directory authorization model to support generalized resources (pages, dashboards, datatypes)
* Adds support for parsing web access and dashboard access from `web_report_access` field
* Adds `CenterUserEntry` class with study-specific authorizations for center users
* Adds `ActiveUserEntry` class with general authorizations for non-center users
* Adds general authorization support for page and dashboard resources
* Refactors `StudyAccessMap` to handle both study-specific and general authorizations
* Removes `nacc_data_platform_access_information_complete` field from directory authorization model
* Removes validation check for survey completion status - now relies on REDCap report filtering
* Adds exception handling for user entry validation errors with error event tracking
* Replaces silent failure check with assertion for better error detection during development

## 2.4.1

* Improves error notification emails with clickable project links
* Adds project name in format `group/project` (e.g., `nacc/user-admin`) to error notifications
* Adds direct URL link to project in Flywheel for easier access to error CSV files
* Populates `center_id` and `registry_id` columns in error CSV when data is available

## 2.4.0

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)
* Changes error notification system to export errors to CSV file instead of sending large email notifications
* Adds CSV export functionality that creates `directory-pull-errors.csv` with detailed error information
* Replaces consolidated email notifications with simple notification email that references the CSV file
* Improves scalability by avoiding AWS SES message size limits for large error sets
* Provides downloadable error reports that can be reviewed in spreadsheet applications

## 2.3.0

* Adds automatic notification batching to handle large error notifications
* Splits notifications exceeding AWS SES 256 KB limit into multiple emails
* Adds batch indicators (e.g., "batch 1/3") to batched notifications
* Prevents notification failures when processing many directory entries with errors

## 2.2.2

* Fixes email notification template to display affected user count and list
* Adds `affected_users_count` field to notification data model
* Updates AWS SES template documentation with correct variable names
* Adds section to list individual affected user emails in notifications

## 2.2.1

* Consolidates notification parameter configuration to use single path `/prod/notifications`
* Updates `NotificationParameters` to include both `sender` and `support_emails` as required fields
* Renames `sender_path` parameter to `notifications_path` in manifest
* Removes redundant `support_emails_path` parameter

## 2.2.0

* Adds automated error notification system with consolidated email notifications to support staff
* Adds event collection and categorization for directory processing errors
* Adds support for configurable support email addresses via Parameter Store
* Adds integration tests for error handling scenarios

## 2.1.2

* Fixes how authorization for genetic data maps to apoe, so study is set to ncrad.

## 2.1.1

* Changes handling of p30 biomarker and genetic authorizations so that they map to ncrad and niagads studies instead of adrc.
  This matches project structure in the system.
* Adds field validation to all authorization flags in the directory authorizations.
  
## 2.0.4

* Add logging when directory records are ignored.
* Change logging of ignored data types

## 2.0.2

* Update directory authorization model to match directory record.
* Use email if auth email is not given.
* Only export non-None fields.
  
## 2.0.0

* Adds this CHANGELOG
* Changes directory entry and user model to match changes to authorizations in NACC directory.
* Updates to pull REDCap API code from library instead of common
* Updates to use local ssm_parameter_store

## 1.0.3 and earlier

* Undocumented
