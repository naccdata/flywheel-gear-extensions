# Changelog

All notable changes to this gear are documented in this file.

## 1.4.3
Updates module pattern to support B1a ingest

## 1.4.2
* Updates to support legacy ingest pipeline
* Evaluates subsequent visits only for longitudinal modules
* Rebuilt for event logging updates
  
## 1.4.1
* Fixes a bug in updating the visit error log
  
## 1.4.0
* Resets QC status and re-evaluates subsequent visits and modules
  
## 1.3.0
* Rebuilt for form ingest configs update
  
## 1.2.7
* Rebuilt for reset error log content in read failure
  
## 1.2.6
* Rebuilt for ssm-parameter-store update
* Rebuilt for new preprocessing checks in config

## 1.2.5
* Updates error metadata to include date and naccid
  
## 1.2.4
* After finalizing alerts, re-process any subsequent visits for the same module 
  
## 1.2.3
* Rebuilding for API call retries
  
## 1.2.2
* Fixes bug where automatic retries were not being detected 

## 1.2.1
* Fixes bug where Flywheel ID was being passed instead of the file ID on system error

## 1.2.0
* Adds functionality for handling multiple pipelines (submission, finalization)
* Updates to read in files with `utf-8-sig` to handle BOM encoding

## 1.1.0
* Adds support for standalone forms submission
* Strips leading zeros from PTID in error log name
  
## 1.0.1
* Upgrades to dependencies
  
## 1.0.0
* Checks for valid UDS input before proceeding with LBD/FTLD validation
* Updates pre-processing error codes
  
## 0.1.10
* Refactors to use gear-specific `QCGearConfigs`

## 0.1.9 - 1.1.6
* Refactors to move logic related to triggering gears to `common/gear_execution/gear_trigger` and pull from there
* Refactors to move logic related to polling jobs to `common/jobs/jobs` and pull from there

## 0.1.5
* Update error reporting - move error metadata to visit error log files stored at project level.
  
## 0.0.3
* Updates QC gear configs
  
## 0.0.1
* [#91](https://github.com/naccdata/flywheel-gear-extensions/pull/91) Initial version - gear for coordinating QC checks for a participant
* [#102](https://github.com/naccdata/flywheel-gear-extensions/pull/102) Form QC Checker updates
* Adds this CHANGELOG
