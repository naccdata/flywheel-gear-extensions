# Changelog

All notable changes to this gear are documented in this file.

## 1.1.0
* Adds email notification on failure

## 1.0.1
* Sets the enrollment date to MDS/BDS visit date if no UDS initial visit available.

## 1.0.0
* Production release
* Sets the enrollment date to the initial visit date for the subject.
* Adds `legacy` flag to enrollment record
  
## 0.0.4
* Cleans up logging, adds error handling to ID creation process.

## 0.0.3
* Removes unused instantiation of `error_writer` in `process_legacy_identifiers`

## 0.0.2
* [#31](https://github.com/naccdata/flywheel-gear-extensions/pull/131) initial build of the gear
* Updates formatting based on linting
* Added `dry_run` flag to allow testing without making changes to Flywheel
* Improved error handling and logging for identifier validation
* Added support for AWS SSM parameter store for credentials
* Updated processing flow to handle new and existing enrollments
* Added unit tests for `process_legacy_identifiers` function
* Improved type safety and validation for identifier processing

## 0.0.1
* Adds this CHANGELOG
* Adds initial README