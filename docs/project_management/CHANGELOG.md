# Changelog

All notable changes to this gear are documented in this file.

## 2.0.1

* Changes study to capture enrollment-pattern for centers within an affiliated study.
* Only creates pipelines for an affiliated study in a center where separate enrollment is designated.
* Moves permission management for study into project and group creation.

## 1.1.1

* Changes `CenterGroup.add_project` so that `project.info.adcid` of the new project is set to the ADCID for the center.
* Updates to read in files with `utf-8-sig` to handle BOM encoding

## 1.0.7

* Update python dependencies

## 1.0.6

* Adds this CHANGELOG
* Fixes an access error in the implementation of the study mapping.
* Replaces the study mapping classes with an implementation of the neglected StudyVisitor abstract class.

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
