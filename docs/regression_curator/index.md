# Regression Curator

Runs a regression test between curated projects and the QAF and MQT baseline files.

## Workflow

This gear uses the same framework as the `attribute_curator`, but instead uses `common/src/curator/regression_curator.py`. Currently it also only runs over `*UDS.json` files since the QAF is UDS-specific, and assumes the project has already been curated by `attribute_curator`.

Preparation steps:

1. Localize the QAF/MQT baseline files from S3, and convert to dicts mapping NACCID_VISITDATE (QAF) or NACCID to a dict-representation of the CSV record
	1. In the case of the QAF, this will filter out any columns that are not `NACC*`, `NGDS*`, or provided by the `keep_fields` config
2. QAF is used as a baseline for the file-level derived variables (focusing only on variables under `file.info.derived`), whereas MQT is used as a baseline for all subject-level variables

Regression curation steps:

1. Create a data view of the project, filtering on the provided `filename_pattern` config (defaults to `*UDS.json` for all UDS files)
2. For each subject, aggregate each file into a MinHeap based on order determined by file type (scope) and date
3. Multiprocess by subject. For each subject
	1. Run a regression test against `subject.info` using the MQT baseline
   	2. Run a regression test against `file.info` for each file in the heap using the QAF baseline
4. Keep track of errors - if errors are found, writes to `regression_errors.csv` (defined by `error_outfile` config) and uploads it to the curated project
