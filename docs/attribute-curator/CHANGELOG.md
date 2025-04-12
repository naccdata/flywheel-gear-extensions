# Changelog

All notable changes to this gear are documented in this file.

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
  