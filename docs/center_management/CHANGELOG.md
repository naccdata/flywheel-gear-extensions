# Changelog

All notable changes to this gear are documented in this file.

## Unreleased
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.1.4
* Rebuilt for ssm-parameter-store update
* Refactors role assignment for groups.
* "Pipeline ADCIDs" are no longer "centers".

## 1.1.1

* Add "audit" to list of custom roles.
* Restores tags to CenterInfo model. Previous changes were failing.
* Updates to read in files with `utf-8-sig` to handle BOM encoding

## 1.0.6
* Fix center map index type
  
## 1.0.5

* Upgrades to dependencies
  
## 1.0.4

* Upgrades to dependencies

## 1.0.3

* Bugfixes to avoid breaking metadata serialization from `centers.center_info.CenterInfo`
    * Renames `center_id` back to `group`
    * Avoids pushing `tags` to `metadata` group

## 1.0.2

* [#109](https://github.com/naccdata/flywheel-gear-extensions/pull/109) Moves the `add_study` behavior from `CenterGroup` to `StudyMapping`, keeping the project creation in `CenterGroup`
* Consolidate `projects.study.Center` and `centers.naccgroup.CenterInfo` to `centers.center_info.CenterInfo` and updates gear to utilize it
* Adds this CHANGELOG

## [1.0.1](https://github.com/naccdata/flywheel-gear-extensions/commit/aa620caf2b6ce8451bdccd1e3719ea2ddeb1d95c)

* [#105](https://github.com/naccdata/flywheel-gear-extensions/pull/105) Fixes error introduced by changing YAML input pattern
    * Removes `get_object_list` method that reads objects from a YAML file
* [#106](https://github.com/naccdata/flywheel-gear-extensions/pull/106) Fixes group permissions exception
    * Updates FW proxy call to `add_group` that can throw exception if user doesn't have permission to access the existing group

## 1.0.0

* [#101](https://github.com/naccdata/flywheel-gear-extensions/pull/101) Initial version; factored out from the project management gear
    * Isolates center group creation in the center management gear
    * Removes center management tasks from the project management gear
