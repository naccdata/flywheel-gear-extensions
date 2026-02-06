# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## Unreleased

* Moves the `TemplateProject` class’s static `__copy_file` method to `utils.files.copy_file` so other gears can access that functionality

## 2.0.1
* Rebuilt for ssm-parameter-store update
  
## 2.0.0

* Changes template project label matching projects to use label w/o the `-template` suffix and no reorganization.

## 1.1.0

* Changes templating so that user permissions are not copied.

## 1.0.6

* Fix center map key type

## 1.0.5

* Changes call to FWClient.put for project app management to use parameter `json` instead of `data` for the payload.
  
## 1.0.4

* Updates template pattern regex to `^((\w+(?:-[\w]+)*)-)?(\w+)-template$` (previously `^((\w+)-)?(\w+)-template$`) which allows matches on data types with dashes in them

## 1.0.3

* Updates to support distribution projects
* Adds `adcid` and to the value map for template replacement

## 1.0.2

* Fixes template pattern generation to handle template labels that don't have a
  datatype (e.g., 'accepted-template')

## 1.0.1

* Functionally the same as 1.0.0 but tweaks some build details

## 1.0.0

* [#61](https://github.com/naccdata/flywheel-gear-extensions/pull/61) 
  * Modifies templating to apply a single template project to matching projects:
    1. uses centers in nacc/metadata to identify groups rather than using tags, and
    2. applies the template project identified in the gear manifest config
  * Removes method for discovering template projects
  * Adds the CHANGELOG

## 0.0.17 and earlier

* Undocumented
