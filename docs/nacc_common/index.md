# nacc-common Python package

Defines the nacc-common package (formerly part of data-platform-demos, and formerly of nacc-common repo.)

This is a package of utilities that can be used by the centers accessing the NACC Data Platform to pull information about submissions.
The package is based on the `flywheel-sdk` package.
We encourage using these functions to avoid situations where data organization might be changed.

Distributions can be accessed via each [release](https://github.com/naccdata/nacc-common/releases) on GitHub.

## Using the package

You can use the release directly by referencing the release files in your package manager.
For instance, adding the following line to `requirements.txt` for use with [pip](https://pip.pypa.io/en/stable/topics/vcs-support/#git)

```text
nacc-common@ https://github.com/naccdata/nacc-common/releases/download/v1.1.2/nacc_common-1.1.2-py3-none-any.whl
```

will include the 1.1.1 release of the package (as a wheel distribution) as a dependency.
The format of the URL stays consistent, so to use a newer version of the package replace the version number.

Most package managers use a similar format to add packages directly from GitHub.
