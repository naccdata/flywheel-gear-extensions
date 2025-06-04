# Changelog

All notable changes to this gear are documented in this file.

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
