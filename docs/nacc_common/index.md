# nacc-common Python package

Utilities for centers accessing the NACC Data Platform to pull information about submissions.
Based on the `flywheel-sdk` package.
We encourage using these functions to avoid situations where data organization might be changed.

Formerly part of [data-platform-demos](https://github.com/naccdata/data-platform-demos), then the standalone nacc-common repo, now part of [flywheel-gear-extensions](https://github.com/naccdata/flywheel-gear-extensions).

## Requirements

- Python 3.10, 3.11, or 3.12
- `flywheel-sdk>=20.0.0`
- `pydantic>=2.5.2,<3`
- `python-dateutil>=2.5.3,<3`

## Using the package

Distributions can be accessed via each [release](https://github.com/naccdata/nacc-common/releases) on GitHub.

You can use a release directly by referencing the release files in your package manager.
For instance, adding the following line to `requirements.txt` for use with [pip](https://pip.pypa.io/en/stable/topics/vcs-support/#git):

```text
nacc-common@ https://github.com/naccdata/nacc-common/releases/download/v3.0.0/nacc_common-3.0.0-py3-none-any.whl
```

The format of the URL stays consistent, so to use a newer version of the package replace the version number.

Most package managers use a similar format to add packages directly from GitHub.

## Modules

- `nacc_common.data_identification` — Data identification models (`DataIdentification`, `ParticipantIdentification`, `VisitIdentification`, `FormIdentification`, `ImageIdentification`)
- `nacc_common.error_models` — QC error and validation models (`FileQCModel`, `FileError`, `GearTags`)
- `nacc_common.form_dates` — Date parsing and conversion utilities
- `nacc_common.pipeline` — Pipeline project lookup utilities
- `nacc_common.center_info` — Center information lookup
- `nacc_common.qc_report` — QC report visitor classes for generating reports
- `nacc_common.error_data` — Error and status data extraction from projects
- `nacc_common.field_names` — Common field name constants

## QC Metadata and Gear Tagging Conventions

For detailed documentation of the QC metadata structure, gear tagging conventions, and which gears use which mechanisms, see the [QC Conventions](qc-conventions.md) reference page.
