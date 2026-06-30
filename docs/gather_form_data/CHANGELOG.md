# Changelog

All notable changes to this gear are documented in this file.

## 0.2.0

* Adds `formver_split` config option to split output CSVs by form version (one file per module/formver pair with version-specific columns)
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 0.1.5

* Fix UnboundLocalError in DataRequestVisitor.visit_row when validation fails

## 0.1.4

* Initial version of the gather-form-data gear, which pulls participant data across centers.
* Adds this CHANGELOG
