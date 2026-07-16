# Pipeline Event Logger Changelog

## 0.2.0

* Discriminated field mapping for QC error extraction with three mapping types: `ListFieldMapping` (list-of-dicts), `StringFieldMapping` (string explanations), and `NoneFieldMapping` (null data on failure)
* String check data used directly as error message; null data with non-PASS state synthesizes a generic failure message
* State guard on `StringFieldMapping` for edge case handling
* Added gear configuration files for deployment

## 0.1.1

* Fix VisitEvent serialization: `modality` field is now included in serialized dicom events
* Rebuilt with forward-compatible event field passthrough

## 0.1.0

- Initial release
- Read QC outcomes from upstream gear metadata (`file.info.qc.{gear_name}`)
- Generic QC metadata reader (`GearQC`, `GearQCResult`) independent of form-specific models
- Config-driven error extraction (`error_configs`) with field mapping to support arbitrary upstream gear error formats
- Update project-level QC status log attributed to the upstream gear
- Optionally capture VisitEvent to S3 based on configurable outcome-to-action mapping
- Support for `dry_run` mode to skip write operations
- Timestamp resolution: prefers `file.info.validated-timestamp`, falls back to `file.modified`
