# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 3.4.0

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
