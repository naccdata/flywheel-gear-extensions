# Changelog

All notable changes to this gear are documented in this file.

## Unreleased
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 2.1.10
* Reverts StudyModel.datatypes to List[str]

## 2.1.9
* Adds retrospective-form project to center ingest projects metadata.
  
## 2.1.8
* Adds pipeline ADCID to retrospective project custom info.

## 2.1.7
* Rebuilt for ssm-parameter-store update
* Changes study model so that must assign a "pipeline ADCID" for separate enrollment.

## 2.1.1

* Fixes bug in logging message in study mapping.
  
## 2.1.0

* Changes error handling in pipeline project creation so that it logs errors instead of raising an exception. None of these scenarios imply failure for the gear.
* Refactors project creation in group adaptor combining configuration that had been repeated across center and study group add_project methods.
* Refactors pipeline project creation in study mapping to ensure a common process and avoid awkward divergence.
* Adds flag to study model to indicate whether the study has legacy data, and changes study mapping to use this as indicator to create retrospective pipelines.

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
