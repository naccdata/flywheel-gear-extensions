# Changelog

All notable changes to this gear are documented in this file.

## 0.4.1

* Updates `nacc-attribute-deriver` to `1.4.1`
* Updates to handle MEDS
* Splits out scheduler models - updates curation `post_process` to take in `FileModel` instead of string `file_id` so it can access the filename without making an API call
* Adds `debug` argument to reduce verbosity of logging statements

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
  