# Changelog

All notable changes to this gear are documented in this file.

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
