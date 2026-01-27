# Changelog

All notable changes to this gear are documented in this file.

## Unreleased
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.2.6
* Bug fixes and improvements
* Rebuilt for event logging updates

## 1.2.5
* Removes whitespace from data values

## 1.2.4
* Rebuilt for reset error log content in read failure

## 1.2.3
* Rebuilt for ssm-parameter-store update
* Rebuilt for error metadata updates
  
## 1.2.2
* Remove gear failure on missing tag
* Rebuilding for API call retries

## 1.2.1
* Catches and reports failure on non-UTF-8-compliant files (instead of crashing)

## 1.2.0
* Adds functionality for handling multiple pipelines (submission, finalization)

## 1.1.2
* Fixes a bug in saving error metadata
  
## 1.1.1
* Adds CSV header validation - duplicate columns and empty columns
* Checks whether the number of columns in data row matches the number of columns in header
  
## 1.1.0
* Formats the input file: remove BOM, change headers to uppercase, remove REDCap specific columns
  
## 1.0.3
* Upgrades to dependencies
  
## 1.0.2
* Updates pre-processing error codes
  
## 1.0.1
* Refactors to use gear-specific `FormSchedulerGearConfigs`

## 1.0.0

* Initial version
* Adds the `gear_execution/gear_trigger` common code to handle triggering of gears
* Adds this CHANGELOG
