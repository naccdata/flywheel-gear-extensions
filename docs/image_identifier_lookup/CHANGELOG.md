# Changelog

All notable changes to this gear are documented in this file.

## 0.1.0

* Added zip archive support for DICOM input files
* Added short-circuit path: skips DICOM file extraction when NACCID, PTID, study date, and modality are already available from Flywheel custom info
* Reads previously stored dicom_metadata from subject.info to avoid redundant file access on re-runs
* Introduced LookupContext model to consolidate extracted data and drive workflow decisions
* Refactored main orchestration into ImageIdentifierLookup class for cleaner separation of concerns

## 0.0.2

* Fixed gear startup crash by initializing GearEngine with parameter store for AWS SSM credential access

## 0.0.1

* Initial release of image-identifier-lookup gear
* Performs NACCID lookups for DICOM images uploaded to the NACC Data Platform
* Extracts patient identifiers from DICOM files using pydicom
* Supports identifier lookup from both subject label and DICOM PatientID tag
* Updates subject metadata with NACCID
* Creates QC status logs with format: `{ptid}_{date}_{modality}_qc-status.log`
* Implements event capture for submission tracking
* Supports dry run mode for testing
* Configurable database mode (prod/dev)
* Comprehensive error handling and validation
* Idempotency checks to skip redundant lookups
* File QC metadata tagging
* Uses Python 3.12 and fw-gear package
