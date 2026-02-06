# Changelog

All notable changes to this gear are documented in this file.

## 1.2.2
* Rebuilt for ingest config updates
  
## 1.2.1

* Fixes event logging for forms without visitnum (milestone/NP forms)
* Adds test coverage for milestone and NP form types

## 1.2.0

* Adds event capture for pass-qc events during finalization queue processing
* Pass-QC events are logged to S3 for visits that successfully complete all QC checks
* Uses QC status log files to determine pass/fail status
* Updates to Python 3.12 and switches to use `fw-gear` instead of `flywheel-gear-toolkit` (now deprecated)

## 1.1.2

* Rebuilt for ssm-parameter-store update

## 1.1.1

* Adds log message to prevent gear being unresponsive

## 1.1.0

* Adds functionality for handling multiple pipelines (submission, finalization)
  
## 1.0.5

* Updates to process all files in a given queue before moving to next queue/module
  
## 1.0.4

* Updates retrieving receiver's email address for submission completion notifications
  
## 1.0.3

* Upgrades to dependencies
  
## 1.0.2

* Updates source email for submission completion notifications
* Moves `wait_for_submission_pipeline` to `JobPoll.wait_for_pipeline` and uses that

## 1.0.1

* Updates pre-processing error codes

## 1.0.0

* Initial version; adds `jobs` to common code
* Adds this CHANGELOG
