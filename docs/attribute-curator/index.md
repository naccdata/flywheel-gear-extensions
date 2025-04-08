# Attribute Curator

Curates subject- and file-level attributes with values derived from file attributes.

Uses the [nacc-attribute-deriver](https://github.com/naccdata/nacc-attribute-deriver) package.

When run on a project, this gear pulls all of the files with the file suffix from the config (defaults to JSON files) and organizes them by subject.
The gear then runs the a curation process on all of the files for a subject using an order determined by file type and date.
Each file is curated using the attribute deriver in order over the custom information of the subject and the data file.

The curation order needs to be kept consistent with the rules in the attribute deriver package.
At the moment, basically UDS form files need to be visited after all other files to ensure that NACC derived variables can be set.

