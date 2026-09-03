# Changelog

All notable changes to this gear are documented in this file.

## 0.3.1

* Treat unresolved NACCIDs as warnings instead of errors — the gear now always writes output files for resolved participants rather than suppressing all output when any identifier is unrecognized

## 0.3.0

* Refactors NACCID resolution from sequential per-row API calls to batched OR-list queries, reducing API calls by ~100x for large request files
* Adds `batch_size` config option (default 100) to control OR-list query batch size for subject resolution and file queries
* Adds `reload_workers` config option (default 10) to control concurrent threads for reloading file metadata
* Duplicate NACCIDs in the request CSV are now deduplicated before resolution (each unique NACCID is resolved once rather than once per row)

## 0.2.1

* Pins flywheel-sdk to 22.0.0 to fix deserialization crash caused by missing `Avatars` model in SDK 22.1.0+

## 0.2.0

* Adds `formver_split` config option to split output CSVs by form version (one file per module/formver pair with version-specific columns)
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 0.1.5

* Fix UnboundLocalError in DataRequestVisitor.visit_row when validation fails

## 0.1.4

* Initial version of the gather-form-data gear, which pulls participant data across centers.
* Adds this CHANGELOG
