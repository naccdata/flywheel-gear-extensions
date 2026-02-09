# Changelog

All notable changes to this gear are documented in this file.

## 1.7.2
* Updates module pattern to support B1a ingest
  
## 1.7.1
* Updates to support legacy ingest pipeline
* Rebuilt for ingest config updates
* Bug fixes and improvements
* Rebuilt for event logging updates

## 1.7.0
* Reprocesses duplicate visit if failed to copy existing QC metadata

## 1.6.0
* Adds NP vs UDS checks
* Rebuilt for form ingest configs update
  
## 1.5.1
* Supports having study suffix in retrospective-form project label
* Rebuilt for reset error log content in read failure
  
## 1.5.0
* Rebuilt for ssm-parameter-store update
* Adds new NP/MLST-related preprocessing checks (025, 026, and 027)
* Adds `preprocess.preprocessor_helpers.py` which includes helper preprocessor classes
    * Refactors how error codes are written to reduce redundancy
* Updates error metadata to include date and naccid
  
## 1.4.5
* Updates pre-processing error messages
* Refactors FormPreprocessor class

## 1.4.4
* Rebuilding for API call retries
  
## 1.4.3
* Updates to parameterize the key to pull visit date from (uses `date_field` in `form-date-module-configs.json`)

## 1.4.2
* Updates `update_file_info_metadata` to also ignore empty strings

## 1.4.1
* Rebuild for handling multiple pipelines (submission, finalization)
* Updates to read in files with `utf-8-sig` to handle BOM encoding

## 1.4.0
* Adds support for standalone forms submission
* Strips leading zeros from PTID in error log name
  
## 1.3.3
* Removes pre-processing checks on visit number ordering

## 1.3.2
* Fixes a bug in visitnum comparison in pre-processing checks
* Upgrades to dependencies
  
## 1.3.1
* Moves the optional forms list to ingest configurations
  
## 1.3.0
* Relaxes the PTID format check
  
## 1.2.1
* Fixes a bug in retrieving module label from file suffix
  
## 1.2.0
* Cross-validates the records within the batch CSV file

## 1.1.2
* Changes the transformation schema format to only include unique fields
* Adds LBD/FTLD pre-processing checks
* Updates pre-processing error codes

## 1.1.0 - 1.1.1
* Adds pre-processing checks
  
## 1.0.5
* Updates error reporting - move error metadata to visit error log files stored at project level
  
## 1.0.2
- Removes GearBot client
- Changes acquisition file naming schema

## 1.0.0

- Moves form-specific functionality of csv-to-json-transformer to form-transformer gear
- Adds transformer schema as input file

## 0.0.11 (from CSV-to-JSON-transformer)
- Normalizes the visit date to `YYYY-MM-DD` format
- Apply module specific transformations
- Creates Flywheel hierarchy (subject/session/acquisition) if it does not exist
- Converts the CSV record to JSON
- Check whether the record is a duplicate
- If not duplicate, upload/update visit file
- Update file info metadata and modality
- For each participant, creates a visits pending for QC file and upload it to Flywheel subject (QC Coordinator gear is triggered on this file)