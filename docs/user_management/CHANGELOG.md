# Changelog

All notable changes to this gear are documented in this file.

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
