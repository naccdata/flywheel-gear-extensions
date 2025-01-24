# Changelog

All notable changes to this gear are documented in this file.

## 1.2.3
* Updates enrollment qc workflow - writes passed visits to a new file to trigger identifier provisioning.

## 1.2.0
* Updates error reporting - move error metadata to visit error log files stored at project level.
  
## 1.1.7

* Changes module label to uppercase for looking up previous visits in Flywheel
  
## 1.1.5 and 1.1.6

* Fixes string to int comparison when checking if C2 or C2T causing it to always skip C2T

## 1.1.4

* Updates `nacc-form-validator` to `1.4.1` which fixes tuple index error and implements "isclose" for comparing float values
* Caches fetching of previous visit record for subject
* Fixes some some minor typos

## 1.1.0

* Update loading rule definitions from S3 - skipping C2 or C2T definition depending on the version submitted
* Defines the `is_valid_adcid` method in the `DataStoreHelper` class - checks whether provided ADCID is in current list of ADCIDs
* Implements `get_previous_nonempty_record` method in the `DataStoreHelper` class - retrieves the previous record where specified fields are NOT empty
* Updates to use nacc-form-validator [v0.4.0](https://github.com/naccdata/nacc-form-validator/releases/tag/v0.4.0)

## 1.0.4

* Defines the `is_valid_rxcui` method in the `DataStoreHelper` class - adds the `rxnorm` common code to support this and future gears that may need to access the RxNorm API

## 1.0.0

* Update to use nacc-form-validator [v0.3.0](https://github.com/naccdata/nacc-form-validator/releases/tag/v0.3.0)
* Rename/refactor `FlywheelDatastore` class to `DatastoreHelper` to allow more general operations
* Add `compute_gds` as a composite rule to match new GDS score validation

## 0.0.32

* [#102](https://github.com/naccdata/flywheel-gear-extensions/pull/102) Form QC Checker updates
	* Add functionality to update/reset failed visit info in subject metadata
	* Updates how to access rule definitions in S3 - use `nacc-flywheel-gear` user credentials
	* Update optional form validation for non-strict mode
	* Update `FlywheelDatastore` class functionality - retrieve legacy module info from Flywheel admin group metadata project
	* Check whether there's a failed previous visit before evaluating the current visit
	* Move dataview creation/reading to FW proxy class

## 0.0.31

* [#100](https://github.com/naccdata/flywheel-gear-extensions/pull/100) Update to use `nacc-form-validator` v0.2.0

## 0.0.30

* [#89](https://github.com/naccdata/flywheel-gear-extensions/pull/89) Adds support for optional forms validation
	* Uses `optional_forms.json` to define optional forms, and load correct definition file dependin on the value of the **mode** variable for the respective form

## 0.0.29 and earlier

* Undocumented
