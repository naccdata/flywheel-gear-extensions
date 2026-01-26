# Changelog

All notable changes to this gear are documented in this file.

## Unreleased
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.1.0
* Rebuilt for ssm-parameter-store update
* Updates to use new center metadata structure for studies
  
## 1.0.0
* Updates to pull REDCap API code from library instead

## 0.1.3
* Fix center map key type

## 0.1.1 - 0.1.2
* Saves updated REDCap metadata in a yaml file in admin project
* Adds dry run option to scrape existing metadata and save to yaml file
  
## 0.1.0
* Refactors main method to simplify code.
* [#96](https://github.com/naccdata/flywheel-gear-extensions/pull/96) Automates REDCap user management
    * Adds the gearbot user with NACC developer permissions when creating a new project
* [#108](https://github.com/naccdata/flywheel-gear-extensions/pull/108) Fixes an issue with the design of `REDCapConnection` to have a `get_project` method, which creates a circular dependency
    * Moves `get_project` to a create method in `REDCapProject`
* Adds this CHANGELOG
* Initial version
