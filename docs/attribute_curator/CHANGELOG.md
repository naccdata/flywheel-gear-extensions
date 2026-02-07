# Changelog

All notable changes to this gear are documented in this file.

## 1.1.2 (Unreleased)

* Reverts `rxclass_concepts` to being an input file now that Batch Scheduler (`1.2.0+`) can support input files; removes gear's reliancy on the gearbot
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.1.1

* Updates `nacc-attribute-deriver` to `2.0.0`
* Updates to keep track of scope in `ProcessedFile` so it only has to be calculated once
* Updates to handle BDS and COVID scopes

## 1.1.0

* Updates `nacc-attribute-deriver` to `2.0.0rc5`
* Refactors to only push data at end of subject heap in order to reduce number of API calls
* Skip curation of files that failed their scopes' QC metrics to account for some things accidentally getting copied over
* Ensures the curation tag is only applied to files that were successfully curated
* Writes errors to file instead of throwing error and failing gear
* Adds `uds-participant` tag to all UDS subjects

## 1.0.3 - 1.0.5

* RC versions of `nacc-attribute-deriver` to `2.0.0rc*` which handles various minor bugs encountered running on full data

## 1.0.2 / 1.0.1

* Updates `rxclass_concepts` to be pulled from S3

## 1.0.0

* Updates `nacc-attribute-deriver` to `2.0.0rc1`, which introduces major refactoring and the remaining derived variables + missingness support
* Adds additional form scopes. MP required a few additional refactors:
    * Updates to support curating over dicom and nifti files, and expands the `filename_pattern` to `filename_patterns` to support multiple patterns
    * Adds `img_study_date` to use the `file.info.header.dicom.StudyDate` field for image file ordering
    * Adds `file.info._filename` as temporary metadata added to the table for deriver use (needed for curation of images file locators)
* Queries RxClass API for V4+ A4 derived variable calculations, and passes to the deriver through the table under `_rxclass`
    * Adds optional input JSON `rxclass_concepts` to provide cached results to skip querying, since this step takes a while otherwise
* Adds loop for missingness logic
    * Passes the previous record to the deriver to support missingness needs through the table under `_prev_record`
* Updates function names from `pre/post_process` to `pre/post_curate`
* Parameterizes number of workers

## 0.4.4

* Updates `nacc-attribute-deriver` to `1.4.3`, which fixes mutability bug causing subjects with no pre-existing metadata to not have its curation updated (usually result of isolated form without UDS/BDS/MDS visit and thus no enrollment data)

## 0.4.3

* Update to also catch `MissingRequiredError`

## 0.4.2

* Updates `nacc-attribute-deriver` to `1.4.2`, which exposes curation rules by scope
* Updates backpropagation logic to handle NP and UDS-specific derived variables
* Adds CLS, FTLD, and LBD scopes (scope not yet used in `1.4.2` of `nacc-attribute-deriver` and ignored)
* Reports version of the attribute deriver for better tracking
* Updates to pass `subject_table` (FW subject.info) around heap evaluation instead of reloading on every file, reducing API calls
    * Also ensures/enforces subject metadata is not updated until ALL files have been curated
* Compiles regex for faster execution

## 0.4.1

* Updates `nacc-attribute-deriver` to `1.4.1`
* Updates to handle MEDS (scope not yet used in `1.4.1` of `nacc-attribute-deriver` and ignored)
* Adds `debug` argument to reduce verbosity of logging statements
* Splits out scheduler models - updates curation `post_process` to take in `FileModel` instead of string `file_id` so it can access the filename without making an API call

## 0.4.0

* Updates nacc-attribute-deriver to `1.4.0`
* Updates to tag affiliates

## 0.3.2

* Updates how metadata deletions are handled to reduce overhead
* Fixes DictProxy error on reporting failed files

## 0.3.1

* Updates how the SDK client is set for multiprocessing - gives each worker its own instance
* Updates to keep track of files that failed to be curated instead of just immediately dying, and report at end
* Fixes bug with decorator `api_retry` not returning the returned function value

## 0.3.0

* Adds the `historic_apoe` namespace, which requires a 3rd pass category
* Updates `nacc_attribute_deriver` to `1.3.0`, which fixes several bugs found while regression testing
* Refactored to generalize curation/scheduling workflow
* Refactors to support pre/post-processing passes
    * For Form Curator this is used to back-propogate cross-sectional variables

## 0.2.9

* Wraps subject metadata wiping in retry block

## 0.2.8

* Fixes issue where `<container>.delete_info` fails if there is no metadata

## 0.2.7

* Adds ability to blacklist NACCIDs from being curated
* Adds the `ncrad_samples` scope
* Adds configuration to apply a tag to each curated file, and will skip curation on subsequent passes if the file has this tag
* Adds the `force_curate` config option to force curation regardless, which also wipes the curation metadata

## 0.2.6

* Moves the `get_subject` call to beginning of loop to avoid calling it for every file in the same subject-specific heap

## 0.2.5

* Adds retry of 3 on curating file

## 0.2.4

* Updates `nacc_attribute_deriver` to `1.2.2`
* Removes rows from ViewResponseModel where all fields are null
* Fixes issue where multiprocessing was failing silently on exception

## 0.2.3

* Ignores unexpected files instead of throwing an exception.
* Fixes regular expression used to identify curation passes by file name.
* Updates nacc-attribute-deriver to v1.2.1
  
## 0.1.0

* Initial release for curator gear using the nacc-attribute-deriver package.
* Adds this CHANGELOG
  