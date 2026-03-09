# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Implements general authorization support for non-center-specific resources
  * Enables users to receive Flywheel project access for ADRC Portal pages based on directory permissions
  * Processes page resources and assigns roles to page stub projects in nacc admin group
  * Collects error events for missing projects and authorization map entries
  * Continues processing when errors occur, preventing single failures from blocking other authorizations
* Implements dashboard authorization support for study-specific dashboards
  * Enables users to receive Flywheel project access for dashboard resources based on directory permissions
  * Processes dashboard resources and assigns roles to dashboard stub projects in center groups
  * Completes authorization flow for dashboard resources parsed in version 4.0.0

## 4.0.3

* Fixes Path type handling in input file path retrieval
  * Wraps `context.config.get_input_path()` return values with `Path()` to ensure Path objects
  * Resolves `AttributeError: 'str' object has no attribute 'stem'` when generating error filenames
  * Addresses type mismatch where `fw-gear` library returns strings despite Path type hint

## 4.0.2

* Fixes user entry validation to correctly handle polymorphic user types
  * Updates `UserEntryList` to use union type `list[CenterUserEntry | ActiveUserEntry | UserEntry]`
  * Removes incorrect conditional logic that assumed all active users are center users
  * Enables Pydantic to automatically discriminate between user types based on fields present
  * Allows active users without center affiliation (missing `org_name`, `adcid`, `study_authorizations`) to validate as `ActiveUserEntry`
* Fixes authorization role assignment to prevent `read-only` from overriding custom roles
  * Modifies `AuthMap.__get_roles` to exclude `read-only` from view activities when submit-audit roles are present
  * Prevents Flywheel tools issue where `read-only` role overrides custom roles like `upload` and `curate`
  * Fixes logic bug where empty `submit_roles` list was blocking all view role assignments

## 4.0.1

* Skipped

## 4.0.0

* **BREAKING CHANGE**: Refactors user entry model hierarchy to support general authorizations
  * Renames `ActiveUserEntry` to `CenterUserEntry` for center-affiliated users
  * Creates new `ActiveUserEntry` base class for users with general authorizations
  * Changes `CenterUserEntry` to extend `ActiveUserEntry` and adds `study_authorizations` field
  * Removes `RegisteredUserEntry` class - registration state now tracked via `registry_person` field
* Adds support for general (non-study-specific) authorizations
  * Introduces `Authorizations` model for general resource access
  * Adds `PageResource` and `DashboardResource` types alongside existing `DatatypeResource`
  * Enables authorization parsing for web pages and dashboards at general and study scopes
* Refactors authorization field naming in `DirectoryAuthorizations` for clarity
  * Renames fields to follow pattern: `{scope}_{resource_type}_{resource_name}_access_level`
  * Changes datatype fields (e.g., `adrc_enrollment_access_level` → `adrc_datatype_enrollment_access_level`)
  * Splits `web_report_access` checkbox into separate `general_page_web_access_level` and `adrc_dashboard_reports_access_level`
  * Adds dashboard fields (e.g., `clariti_dashboard_pay_access_level`, `clariti_dashboard_ror_access_level`)
* Improves `StudyAccessMap` to handle multiple resource types
  * Adds `add_general_access()` method for general authorizations
  * Renames `add()` to `add_study_access()` for clarity
  * Adds `get_authorizations()` for general authorizations and `get_study_authorizations()` for study-specific
  * Changes internal storage from `access_level_map` to `study_access_level_map`
* Enhances user registration workflow
  * Changes registration from creating new object to mutating existing entry via `register()` method
  * Stores full `RegistryPerson` object instead of just registry ID string
  * Adds `is_registered` property and `registry_id` property for cleaner access
  * Adds `set_fw_user()` method to attach Flywheel user object to entry
* Refactors user processing pipeline
  * Splits `UpdateUserProcess` into general user updates and `UpdateCenterUserProcess` for center-specific logic
  * Changes process signatures to use `ActiveUserEntry` instead of `RegisteredUserEntry`
  * Adds validation checks for registered state before processing
  * Improves separation of concerns between general and center user authorization
* Adds robust field parsing for authorization resources
  * Implements `__handle_datatype_resource()`, `__handle_page_resource()`, and `__handle_dashboard_resource()` methods
  * Adds support for multi-token resource names converted to kabob-case
  * Improves genetic datatype expansion to multiple studies (NCRAD, GWAS, etc.)
* Improves validation and error handling
  * Adds `convert_adcid()` validator to handle empty strings and "NA" values
  * Makes `adcid` field optional to support non-center users
  * Adds validators for web access and ADRC reports access levels from checkbox field
  * Removes `complete` field requirement from directory authorizations
* Updates gear entry point to use `CenterUserEntry` instead of `ActiveUserEntry` for active users

## 3.4.1

* Improves error notification emails with clickable project links
* Adds project name in format `group/project` (e.g., `nacc/user-admin`) to error notifications
* Adds direct URL link to project in Flywheel for easier access to error CSV files
* Populates `center_id` and `registry_id` columns in error CSV when data is available

## 3.4.0

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)
* Changes error notification system to export errors to CSV file instead of sending large email notifications
* Adds CSV export functionality that creates `{input-filename}-errors.csv` with detailed error information
* Replaces consolidated email notifications with simple notification email that references the CSV file
* Improves scalability by avoiding AWS SES message size limits for large error sets
* Provides downloadable error reports that can be reviewed in spreadsheet applications

## 3.3.0

* Adds automatic notification batching to handle large error notifications
* Splits notifications exceeding AWS SES 256 KB limit into multiple emails
* Adds batch indicators (e.g., "batch 1/3") to batched notifications
* Prevents notification failures when processing many users with errors

## 3.2.2

* Fixes email notification template to display affected user count and list
* Adds `affected_users_count` field to notification data model
* Updates AWS SES template documentation with correct variable names
* Adds section to list individual affected user emails in notifications

## 3.2.1

* Consolidates notification parameter configuration to use single path `/prod/notifications`
* Updates `NotificationParameters` to include both `sender` and `support_emails` as required fields
* Renames `sender_path` parameter to `notifications_path` in manifest
* Removes redundant `support_emails_path` parameter

## 3.2.0

* Adds automated error notification system with consolidated email notifications to support staff
* Adds event collection and categorization for user processing errors
* Adds support for configurable support email addresses via Parameter Store
* Adds integration tests for error handling scenarios

## 3.1.1

* Rebuilt for comanage API changes
  
## 3.1.0

* Change how redcap project authorizations are checked so that each project is checked.
* Change logging so that only logs when user authorizations match no redcap project submission activity.

## 3.0.4

* Fixes check for REDCap authorizations
* Adds authorization application for distribution projects

## 3.0.3

* Fixes contains check for authorizations
* Improves log output of user authorizations

## 3.0.2

* Makes changes to reflect changes to the authorization scheme in the NACC directory. Adds handling of authorizations for particular studies, and expands the allowed datatypes.
  
## 2.1.2

* Rebuilt for ssm-parameter-store update
* Updates to use new center metadata structure for studies
  
## 2.1.0

* Changes authorization mapping lookup so that authorization rules will match a study qualified project if only general pipeline rules are defined.

## 2.0.0

* Changes check for claimed record by relaxing requirement that record includes an OIDC asserted email address.
* Updates to read in files with `utf-8-sig` to handle BOM encoding
* Add error handling for CoManageMessage validation errors in user registry.
* Add error handling for RegistryError errors in user management gear.

## 1.4.10
* Updates to use redcap_api-0.1.1
  
## 1.4.9

* Updates to pull REDCap API code from library instead
* Fixes an error pulling the full list of coperson records when the record count
  is a multiple of the page size.

## 1.4.8

* Find the SSO authentication email from claimed registry record
  
## 1.4.6

* Enable automated REDCap user management based on the permissions set in NACC directory

## 1.4.4

* Change so only enqueues a user entry in created-user queue immediately after creation.
  Prevents multiple emails to users who haven't logged in.

## 1.4.3

* Enable sending "user created" email when "none" is selected for notifications.
* Update python dependencies.
  
## 1.4.2

* Remove premature "changing email" logging

## 1.4.1

* Remove "user has not logged in" logging

## [1.4.0](https://github.com/naccdata/flywheel-gear-extensions/pull/114)

* Changes user management to implement discrete processes over queues of user
  entries from the NACC directory.
* Adds modes for follow-up notifications: send none, send by date, send all.
* Disables REDCap user management
* Adds error handling when adding a user fails in FW
* Adds this CHANGELOG

## 
## 1.1.4 and earlier

* Undocumented
