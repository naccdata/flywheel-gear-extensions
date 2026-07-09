# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Requires the deletion-acknowledgment checkbox (`ack_key`, default `delete_ack`) to be checked
  before a `yes` answer is confirmed; a `yes` without the acknowledgment is treated as missing data
  (reset/skip) and the file is not tagged `PHI-Confirmed`. Adds the `ack_key` config.
* Initial version
* Adds this CHANGELOG
* Implements PHI review finalization: scans completed PHI reader tasks (by protocol) across accessible
  projects, tags the reviewed file `PHI-Confirmed`/`PHI-Not-Found` based on the form response and removes
  `PHI-Found`, then marks the task processed to exclude it from future runs
* Optionally resets a completed task with no usable answer back to `Todo` and clears its response
* Runs without an input file (scheduled, admin-group); all changes are `dry_run`-aware
