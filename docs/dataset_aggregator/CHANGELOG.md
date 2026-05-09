# Changelog

All notable changes to this gear are documented in this file.

## 0.2.1

* More verbose error logging

## 0.2.0

* Differentiate between `freeze_date` and `etl_date`
* Update to report duplicate visits instead of resolving
	* Adds optional configuration JSON to specify which fields a table should match on to identify duplicates
	* Removes identifiers lookup - conflicts should be manually fixed instead
	* Renames `TransferDuplicatesHandler` to `DuplicatesHandler` since it's not necessarily about transfers anymore

## 0.1.1

* Add `snapshot_date`

## 0.1.0

* Initial version
* Adds this CHANGELOG
