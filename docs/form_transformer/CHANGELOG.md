# Changelog

All notable changes to this gear are documented in this file.

## TBD

- n/a

## 1.0.0

- Moves form-specific functionality of csv-to-json-transformer to form-transformer gear.
- Add transformer schema as input file

## 0.0.11 (from CSV-to-JSON-transformer)
- Normalizes the visit date to `YYYY-MM-DD` format
- Apply module specific transformations
- Creates Flywheel hierarchy (subject/session/acquisition) if it does not exist
- Converts the CSV record to JSON
- Check whether the record is a duplicate
- If not duplicate, upload/update visit file
- Update file info metadata and modality
- For each participant, creates a visits pending for QC file and upload it to Flywheel subject (QC Coordinator gear is triggered on this file)