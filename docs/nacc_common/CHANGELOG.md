# Changelog

Documentation of release versions of the `nacc-common` package.

## Unreleased
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

# v2.1.0

* Adds QC status constants (`QC_STATUS_PASS`, `QC_STATUS_FAIL`, `QC_STATUS_IN_REVIEW`) to `error_models` module for consistent status value handling.
* Refactors `ProjectReportVisitor` to use factory pattern instead of stateful `set_visit()` method, improving code maintainability and thread safety.
* Updates `StatusReportVisitor` and `ErrorReportVisitor` constructors to extract visit details from filenames automatically.
* Maintains full backward compatibility for public APIs including `get_status_data()` and `get_error_data()` functions.

# v2.0.1

* Fixes serialization of report objects so uses field name aliases.

# v2.0.0

* Moves the nacc-common code into the flywheel-gear-extensions repo to allow use of same code used for reporting gears used for affiliated studies.
* Changes report columns to match those used in portal downloads.
* Changes distribution build to constrain minimum python version, and adds README and LICENSE files to the build.

# v1.2.5

* Fixes use of error_data which returns a list of error objects.
  
# v1.2.4

* Fixes an issue where error data is returned for approved alerts, by only returning data when status is not pass.

# v1.2.0

* Replaces logging with exceptions
* Adds type stubs to package

# v1.1.4

* Moves package to separate repo.
* Adds status query method.

## Older

For previous releases, see [data-platform-demos](https://github.com/naccdata/data-platform-demos/releases).
