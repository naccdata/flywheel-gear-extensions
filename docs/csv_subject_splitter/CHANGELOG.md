# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.0.6

* Adds `source_file` to file metadata to track provenance
* Updates to read in files with `utf-8-sig` to handle BOM encoding
* Parameterizes required fields

## 1.0.5

* Adds delimiter option
* Does not uppercase extensions

## 1.0.4

* Changes JSONUploader to use the FW project-hierarchy-upsert API endpoint. This requires a device API key, which is stored in the AWS parameter store. So the gear must be run as a gearbot ("credentials condor") on FW. However, the gear does not use the gearbot API key.
* Adds `preserve_case` configuration option - defaults to setting all headers to lowercase and replacing spaces/dashes with underscores
* Does not reupload duplicate files

## 1.0.3

* Changes splitter so that file is uploaded for each row rather than saving all rows and then uploading

## 1.0.2

* Updates `ProjectAdaptor.add_subject` to return the subject if it already exists
* Updates `uploader.JSONUploader` to remove the `allow_updates` parameter - will always update instead

## 1.0.1

* Updates `hierarchy_labels` config to be type `string` instead of type `object`
* Updates `uploads.uploader.JSONUploader` to accept a `allow_updates` parameter (defaults `false`) and, if `false`, throw an error if the subject already exists
* Refactors to use `InputFileWrapper.get_parent_project`
* Removes `assert parameter_store` statement

## 1.0.0

- Redefines the csv-to-json-transformer to csv-subject-splitter gear that splits CSV files using the value in the NACCID column.
  Note: most of 0.0.11 changes are for form split/transform that are specific to the form-transformer gear.
- Adds config parameter for templating of labels for session and acquisition and filename resulting from split.
- Optional input files are allowed to be missing.

## 0.0.11
- Normalizes the visit date to `YYYY-MM-DD` format
- Apply module specific transformations
- Creates Flywheel hierarchy (subject/session/acquisition) if it does not exist
- Converts the CSV record to JSON
- Check whether the record is a duplicate
- If not duplicate, upload/update visit file
- Update file info metadata and modality
- For each participant, creates a visits pending for QC file and upload it to Flywheel subject (QC Coordinator gear is triggered on this file)
