# Changelog

All notable changes to this gear are documented in this file.

## 2.1.1

* Changes handling of p30 biomarker and genetic authorizations so that they map to ncrad and niagads studies instead of adrc.
  This matches project structure in the system.
* Adds field validation to all authorization flags in the directory authorizations.
  
## 2.0.4

* Add logging when directory records are ignored.
* Change logging of ignored data types

## 2.0.2

* Update directory authorization model to match directory record.
* Use email if auth email is not given.
* Only export non-None fields.
  
## 2.0.0

* Adds this CHANGELOG
* Changes directory entry and user model to match changes to authorizations in NACC directory.
* Updates to pull REDCap API code from library instead of common 
* Updates to use local ssm_parameter_store

## 1.0.3 and earlier

* Undocumented
