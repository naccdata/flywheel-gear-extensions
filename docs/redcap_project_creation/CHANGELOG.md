# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* [#96](https://github.com/naccdata/flywheel-gear-extensions/pull/96) Automates REDCap user management
    * Adds the gearbot user with NACC developer permissions when creating a new project
* [#108](https://github.com/naccdata/flywheel-gear-extensions/pull/108) Fixes an issue with the design of `REDCapConnection` to have a `get_project` method, which creates a circular dependency
    * Moves `get_project` to a create method in `REDCapProject`
* Adds this CHANGELOG
* Initial version
