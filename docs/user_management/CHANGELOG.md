# Changelog

All notable changes to this gear are documented in this file.

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
