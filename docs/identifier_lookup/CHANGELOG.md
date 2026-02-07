# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 2.2.2

* Fixes KeyError when processing forms without visitnum column (e.g., Milestones, NP)
* Updates VisitMetadata serializer to handle missing visitnum and date fields
* Adds comprehensive tests for CSV processing without visitnum

## 2.2.0

* Adds event capture for submit events during CSV processing
* Submit events are logged to S3 for each valid CSV row with required fields
* Adds event logging
* Updates to allow distribution projects to run the `nacc` direction
* Adds enum constraints to `database_mode` and `direction` config parameters for better UI validation

## 2.1.0

* Rebuilt for form ingest configs update
  
## 2.0.1

* Resets error log content if failed to read existing content

## 2.0.0

* Changes to use the ADCID from the parent project custom info for the pipeline ADCID. Fails if the ADCID is not set.
* Updates to use new identifier lambda functions with restructured identifiers database
* Updates error metadata to include date and naccid
* Make `form_configs_file` only required for `nacc` direction
* For the `center` direction (reverse lookup), adds sleep of 1 second every 1000 records to reduce connectivity issues
* Rebuilt for new preprocessing checks in config
* Rebuilt for ssm-parameter-store update
  
## 1.2.3

* Rebuilding to call identifier lambda function alias depending on request mode
  
## 1.2.2

* Rebuilding for API call retries
  
## 1.2.1

* Rebuild for handling multiple pipelines (submission, finalization)
* Updates to read in files with `utf-8-sig` to handle BOM encoding

## 1.2.0

* Adds support for standalone forms submission
* Strips leading zeros from PTID in error log name
  
## 1.1.3

* Fix validation of PTIDs to ensure they are stripped of whitespace and leading zeros.

## 1.1.2

* Fix center map key type
  
## 1.1.1

* Upgrades to dependencies
  
## 1.1.0

* Relaxes the PTID format check
  
## 1.0.11

* Fixes a bug in retrieving module label from file suffix
  
## 1.0.10

* Allows underscore in GUID
  
## 1.0.9

* Adds `preserve_case` configuration value (default `false`) to allow preserving case of header keys in output file
* Refactors to use `InputFileWrapper.get_parent_project`

## 1.0.8

* Fixes CSV line number in error reports (exclude header row)
* Updates pre-processing error codes
* Updates GUID format and max length
  
## 1.0.7

* Adds pre-processing check for PTID length

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
