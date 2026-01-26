# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.0.0

* Updates to support full QAF, including missingness values, not just derived variables
* Integrates event logging functionality for enhanced QC status tracking and error reporting

## 0.2.0

* Add support for MRI QAFs
* Adds support for multiple filename patterns

## 0.1.3

* Updates to consider when a field is in the baseline but not derived vars
* Fixes bug that crashed on lists of dicts

## 0.1.2

* Adds `debug` argument to reduce verbosity of logging statements
* Updates MQT regression testing to not be required

## 0.1.1

* Changes type to `analysis`

## 0.1.0

* Initial version
* Refactors curation/scheduling workflow to generalize process for multiple use-cases
* Adds this CHANGELOG
