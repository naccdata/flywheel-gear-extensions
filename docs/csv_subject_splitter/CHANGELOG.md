# Changelog

All notable changes to this gear are documented in this file.

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
