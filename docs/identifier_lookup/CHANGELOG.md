# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* [#30](https://github.com/naccdata/flywheel-gear-extensions/pull/30) Initial version - adds the identifier-lookup gear: reads a CSV with ADCID and PTID on each row, looks up NACCID, if NACCID exists, outputs row to file, if NACCID doesn't exist output error
* [#29](https://github.com/naccdata/flywheel-gear-extensions/pull/29) Adds classes for capturing and outputting errors/alerts to CSV file
* Adds this CHANGELOG
* Changes Identifier Lookup so that it extracts the module name from the filename suffix and inserts it into the output CSV with the column name `module`.
* Change code structure identified by linting

