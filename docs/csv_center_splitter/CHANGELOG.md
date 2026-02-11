# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Adds notification to REDCap email list on pipeline completion
* Moves `generate_project_map` to common code
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 0.2.3

* Bug fixes and improvements

## 0.2.2

* Updates to use generalized `utils.files.get_centers_with_filters` and `JobPoll.wait_for_batched_group` methods
* Updates to read in files with `utf-8-sig` to handle BOM encoding

## 0.2.1

* Fix center map key type
  
## 0.2.0

* Adds scheduling/batching functionality

## 0.1.2

* Adds `include` and `exclude` config options to include/exclude centers as needed

## 0.1.1

* Throws error if staging project cannot be found

## 0.1.0

* Initial version
* Adds this CHANGELOG