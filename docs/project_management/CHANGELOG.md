# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Adds this CHANGELOG

## 1.0.2

* [#105](https://github.com/naccdata/flywheel-gear-extensions/pull/105) Fixes error introduced by changing YAML input pattern
    * Removes `get_object_list` method that reads objects from a YAML file

## 1.0.0

* [#101](https://github.com/naccdata/flywheel-gear-extensions/pull/101) Factors out center management gear from project management gear
    * Isolates center group creation in the center management gear
    * Removes center management tasks from the project management gear
* [#103](https://github.com/naccdata/flywheel-gear-extensions/pull/103) Adds study modes
	* Changes project management gear so that it can create studies with different pipeline patterns, namely `aggregation` and `distribution`

## 0.0.32 and earlier

* Undocumented
