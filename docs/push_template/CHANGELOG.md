# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

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
