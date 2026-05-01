# Pipeline Event Logger Changelog

## 0.1.0

- Initial release
- Read QC outcomes from upstream gear metadata (`file.info.qc.{gear_name}`)
- Update project-level QC status log attributed to the upstream gear
- Optionally capture VisitEvent to S3 based on configurable outcome-to-action mapping
- Support for `dry_run` mode to skip write operations
- Timestamp resolution: prefers `file.info.validated-timestamp`, falls back to `file.modified`
