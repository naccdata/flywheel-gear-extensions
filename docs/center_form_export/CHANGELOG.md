# Changelog

## v0.0.2

- Pins flywheel-sdk to 22.0.0 to fix deserialization crash caused by missing `Avatars` model in SDK 22.1.0+

## v0.0.1

Initial release.

- Export form data for all subjects in a Flywheel group/project without a participant list
- Config-driven: `group_id`, `project_name`, `modules`, `study_id`
- Optional `formver_split` mode producing one CSV per (module, form version) pair
- Optional `include_derived` to include derived variables
- Resilient processing: logs warnings for individual subject failures, continues with remaining subjects
