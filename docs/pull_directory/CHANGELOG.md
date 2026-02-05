# Changelog

All notable changes to this gear are documented in this file.

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
