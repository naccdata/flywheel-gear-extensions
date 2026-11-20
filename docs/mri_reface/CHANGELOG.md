# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Initial version, adapted from an external mri_reface 0.3.5 gear wrapper
* Adds this CHANGELOG
* Builds on the NITRC mri_reface Docker image, adding Python 3.12 so the gear runs as a pex
* Accepts a NIfTI or a zipped single-series DICOM; outputs the refaced NIfTI, the refaced DICOM zip (for DICOM input), and face renders
