# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* [#109](https://github.com/naccdata/flywheel-gear-extensions/pull/109) Moves the `add_study` behavior from `CenterGroup` to `StudyMapping`, keeping the project creation in `CenterGroup`
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
