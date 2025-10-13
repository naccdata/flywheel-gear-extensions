# Changelog

Documentation of release versions of the `nacc-common` package.

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
