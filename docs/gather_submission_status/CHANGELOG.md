# Changelog

All notable changes to this gear are documented in this file.

## 1.4.3

* Relax QC filename pattern: module accepts alphanumeric names (e.g. `B1A`), visitnum accepts any non-underscore characters (including dashes)

## 1.4.2

* Fix QC filename pattern to handle all visitnum formats (plain integers like `7`, zero-padded like `003`, and alphanumeric codes like `FU6`) via updated nacc-common dependency

## 1.4.1

* Add concurrent file reloading with configurable `reload_workers` parameter (default 10) for significantly faster processing of large projects
* Fix qc-status file discovery to match filenames that include a visitnum segment (e.g., `2851_2025-09-02_10.00_uds_qc-status.log`). Previously only legacy filenames without visitnum were found.

## 1.4.0

* Removes hardcoded module name restriction — any module name is now accepted without filtering or warnings
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.3.0

* Merges in changes for nacc-common. Should not affect behavior of the gear

## 1.0.2

* Fixes an error in the submission status/error reporting

## 1.0.0

* Change request to only require the ADCID and PTID, dropping the study.
* Refactor error/status reporting so can be used by other code

## 0.4.0

* Adds generation of an error report from the qc-status logs.

## 0.3.4

* Change so that metadata from qc-status logs is used rather than acquisition files.

## 0.2.1

* Adds visit date to output.
* Moves list of form modules to gear manifest, so that same modules are searched for all participants.
* Add study ID to gear manifest that is used to check for valid study IDs in query file.

## 0.1.3

* Adds gear to pull status details of files in ingest projects for a list of participants
