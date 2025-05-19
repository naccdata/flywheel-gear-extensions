# Attribute Curator

Curates subject- and file-level attributes with values derived from file attributes.

Uses the [nacc-attribute-deriver](https://github.com/naccdata/nacc-attribute-deriver) package.

When run on a project, this gear pulls all of the files with the file suffix from the config (defaults to JSON files) and organizes them by subject.
The gear then runs the a curation process on all of the files for a subject using an order determined by file type (scope) and date.
Each file is curated using the attribute deriver in order over the custom information of the subject and the data file.

The curation order needs to be kept consistent with the rules in the attribute deriver package.
At the moment, basically UDS form files need to be visited after all other files to ensure that NACC derived variables can be set.

## Workflow

Most of this logic is handled in `common/src/curator/scheduling.py` and `common/src/curator/form_curator.py`

1. Create a data view of the project, filtering on the provided `filename_pattern` config (defaults to `*.json` for all JSON files)
2. For each subject, aggregate each file into a MinHeap based on order determined by file type (scope) and date
3. Multiprocess by subject. For each subject
    1. Run each file (in order) through the attribute deriver
    2. Push the results to `file.info` and/or `subject.info`, depending on the specific curation rules applied for that scope
    3. Once curation over all files is done, back-propogate `subject.info.derived.cross-sectional` values back into each UDS file
