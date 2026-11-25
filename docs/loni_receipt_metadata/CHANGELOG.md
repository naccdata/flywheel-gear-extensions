# LONI Receipt Metadata Changelog

All notable changes to this gear are documented in this file.

## 0.0.1

* Initial release
* Reads one upload receipt CSV (`upload_data_<timestamp>.csv`) written by the `loni-upload` gear
* Matches receipt rows to acquisition files by the file ID at the start of the `Directory` basename, and resolves each file to its acquisition
* Writes `acquisition.info.upload_loni.<file_id>` with `file_name`, `upload_id`, `status` and a list of `{loni_uid, upload_date}` for each successfully uploaded file; entries for other files are left unchanged
* Attaches a copy of the receipt, limited to the rows for that acquisition's files, to each acquisition that received an entry; a same-name upload creates a new file version
* Tags the input receipt `loni-receipt-metadata-PASS` or `loni-receipt-metadata-FAIL`
* Failed rows write nothing; the gear processes every row and then fails the job if any row failed
* Supports `dry_run` mode to log what would be written without writing
