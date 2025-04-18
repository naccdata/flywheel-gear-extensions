# Identifier Lookup

The identifier-lookup gear reads participant IDs from a tabular (CSV) input file and checks whether each ID corresponds to a NACCID (the NACC-assigned participant ID). This gear supports two directions: `nacc` and `center`.

If the direction is `nacc`, the input file is assumed to have one participant per row with columns `adcid` (NACC-assigned center ID), and `ptid` (center-assigned participant ID), and will append `naccid` to the output.

If the direction is `center`, the input file is assumed to have one participant per row with a `naccid` column, and will append `adcid` and `ptid` to the output.

The gear outputs a copy of the CSV file consisting of the rows for participants that have NACCIDs, with an added `naccid` column for the NACCID.

If there are any rows where the participant ID has no corresponding NACCID, an error file is also produced.
The error file will have a row for each input row in which participant ID has no corresponding NACCID.

## Environment

This gear uses the AWS SSM parameter store, and expects that AWS credentials are available in environment variables within the Flywheel runtime.
The variables used are `AWS_SECRET_ACCESS_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_DEFAULT_REGION`.
The gear needs to be added to the allow list for these variables to be shared.

## Configuration

Gear configs are defined in [manifest.json](../../gear/identifier_lookup/src/docker/manifest.json).

## Input

The input is a single CSV file, which must have columns `adcid` and `ptid`.

## Output

The gear has two output files.

- A CSV file consisting of the rows of the input file for which a NACCID was found, with an additional `naccid` column if the direction is `nacc` or additional `adcid` and `ptid` columns if the direction is `center`
  - Unless the configuration value `preserve_case` is set to `True`, all header keys will also be forced to lower case and spaces replaced with `_`
- A CSV file indicating errors, and specifically information about rows for which a NACCID was not found.
  The format of this file is determined by the FW interface for displaying errors.



