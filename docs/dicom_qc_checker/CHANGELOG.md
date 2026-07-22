# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Initial version
* Implements DICOM QC status aggregation: reads individual check results from
  `file.info.qc.dicom-qc`, determines aggregate pass/fail status, and tags the file accordingly
* Filters out `job_info` and non-check entries; logs failed check names at WARNING level
* Exits cleanly when QC metadata is absent or contains no valid check results
