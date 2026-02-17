# Changelog

All notable changes to this gear are documented in this file.

## Unreleased
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 2.0.1
* Supports having study suffix in retrospective-form project label
  
## 2.0.0
* Rebuilt for ssm-parameter-store update
* Changes to use the ADCID from the parent project custom info for the pipeline ADCID. Fails if the ADCID is not set.
* Updates to use new identifier lambda functions with restructured identifiers database
  
## 1.1.6
* Rebuilding to call identifier lambda function alias depending on request mode
  
## 1.1.5
* Updates the code to include IT packets when checking for enrollment date
  
## 1.1.4
* Fixes a bug in import
  
## 1.1.3
* Fixes center map key type

## 1.1.0 - 1.1.2
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