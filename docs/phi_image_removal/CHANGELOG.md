# Changelog

All notable changes to this gear are documented in this file.

## Unreleased

* Initial version
* Adds this CHANGELOG
* Implements PHI image removal: for a `PHI-Confirmed` input file, captures the file's details into a
  JSON tombstone, uploads the tombstone (original base name with a `.json` extension) into the same
  acquisition, tags it `PHI-Tombstone`, and deletes the original image
* Orders the actions so the image is never deleted without a tagged tombstone already in place
* No-ops when the confirming tag is absent or a tombstone already exists; all changes are `dry_run`-aware
