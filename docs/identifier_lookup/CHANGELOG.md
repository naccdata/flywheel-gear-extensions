# Changelog

All notable changes to this gear are documented in this file.

## 1.0.6

* Fixes bug where an empty file would be generated if no entries passed

## 1.0.5
* Fixes a bug in error reporting
* Updates identifier lookup error messages and identifier file suffix.

## 1.0.0

* Adds ability to do a reverse lookup on NACCID to find the center IDs.
  Allows injecting the ADCID needed to split a CSV for distribution across centers.

## 0.1.0
* Update error reporting - move error metadata to visit error log files stored at project level.
  
## 0.0.5
* Changes `identifier_mode` gear config to `database_mode`
  
## Unreleased

* [#30](https://github.com/naccdata/flywheel-gear-extensions/pull/30) Initial version - adds the identifier-lookup gear: reads a CSV with ADCID and PTID on each row, looks up NACCID, if NACCID exists, outputs row to file, if NACCID doesn't exist output error
* [#29](https://github.com/naccdata/flywheel-gear-extensions/pull/29) Adds classes for capturing and outputting errors/alerts to CSV file
* Adds this CHANGELOG
* Changes Identifier Lookup so that it extracts the module name from the filename suffix and inserts it into the output CSV with the column name `module`.
* Change code structure identified by linting

