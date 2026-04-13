# Changelog

Documentation of release versions of the `nacc-common` package.

## Unreleased

## v3.0.0

### Breaking Changes

* Replaces `VisitKeys`/`VisitMetadata` with `DataIdentification` using a composition pattern (`ParticipantIdentification`, `VisitIdentification`, `FormIdentification`, `ImageIdentification`).
* Removes bundled Flywheel type stubs from the distribution.
* Requires `python-dateutil`, `pydantic>=2.5.2,<3`, and `typing_extensions>=4.0.0` as explicit dependencies.

### New Features

* Adds `form_dates` module with date parsing and conversion utilities (moved from internal `common/dates`).
* Adds `DataIdentification.from_form_record()`, `from_visit_metadata()`, `from_visit_info()` factory methods.
* Adds `DataIdentification.with_updates()` for backfilling missing fields.
* Adds visitor pattern support via `AbstractIdentificationVisitor`.
* Adds QC status constants (`QC_STATUS_PASS`, `QC_STATUS_FAIL`, `QC_STATUS_IN_REVIEW`) to `error_models`.
* Adds `GearTags` class for managing gear-specific file tags.
* Adds `FileQCModel.get_file_status()` for overall file QC status.
* Adds `ClearedAlertModel` and `ClearedAlertProvenance` models.

### Improvements

* Refactors `ProjectReportVisitor` to use factory pattern instead of stateful `set_visit()` method.
* Updates `StatusReportVisitor` and `ErrorReportVisitor` to extract visit details from filenames automatically.
* Normalizes module and packet fields to uppercase for consistent matching.
* Normalizes date strings in `DataIdentification.from_visit_metadata()` to `YYYY-MM-DD` format.
* Fixes handling of forms without visitnum.
* Supports Python 3.10 through 3.12.

## v2.0.1

* Fixes serialization of report objects so uses field name aliases.

## v2.0.0

* Moves the nacc-common code into the flywheel-gear-extensions repo to allow use of same code used for reporting gears used for affiliated studies.
* Changes report columns to match those used in portal downloads.
* Changes distribution build to constrain minimum python version, and adds README and LICENSE files to the build.

## v1.2.5

* Fixes use of error_data which returns a list of error objects.

## v1.2.4

* Fixes an issue where error data is returned for approved alerts, by only returning data when status is not pass.

## v1.2.0

* Replaces logging with exceptions
* Adds type stubs to package

## v1.1.4

* Moves package to separate repo.
* Adds status query method.

## Older

For previous releases, see [data-platform-demos](https://github.com/naccdata/data-platform-demos/releases).
