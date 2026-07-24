# Changelog

## v0.0.3

- Fixes severe slowness on large centers (e.g. 1h52m for Arizona's ~25k-file retrospective project): replaced per-subject `get_files` queries with queries batched across subject ids (100 per batch, via Flywheel's OR-list filter syntax)
  - An earlier version of this fix issued a single unscoped query per module for the whole project; that was found in local testing to reliably time out on Flywheel's backend for large centers (retried for ~10 minutes then hard-failed with zero output) and was replaced with batching before release
- Adds progress logging (per-module start, and once per subject batch processed) to distinguish a slow-but-running job from a stalled one
- Reloads each batch's files concurrently (10 workers by default, `reload_workers` param) instead of one at a time, since a dataview-based bulk-fetch was found not to be viable (Flywheel's dataview columns only support fixed scalar fields, not the dynamic per-module field sets this gear needs) and per-file `.reload()` calls were confirmed by benchmark to be the dominant remaining cost for modules with many visits per subject (e.g. UDS): ~6.7x faster reload throughput in testing
- `batch_size` and `reload_workers` are both explicit, overridable parameters on `ModuleDataGatherer.gather_project_data`, and further exposed as gear config fields (`batch_size`, `reload_workers` in `manifest.json`), rather than a hardcoded constant
- `batch_size=100` validated via a sweep (25/100/200) against a small center and a large one (`retrospective-form`, ~25k files): 25 was slower everywhere; 200 was faster on the small center but a wash on the large one (reload volume dominates there, not query count) and did not reproduce the earlier timeout — confirms 100 has real margin rather than sitting at a fragile edge; kept as the default
- Writes each module's output file(s) immediately after that module finishes gathering, instead of waiting until every module has gathered — a later module's unrecoverable failure no longer discards an earlier module's already-completed output
- Reuses one thread pool across all of a module's batches instead of constructing/tearing one down per batch
- Validated end-to-end against Arizona's `retrospective-form` project (3,003 subjects, ~13,980 sessions, a large legacy-import center — not confirmed to be the largest overall): 16m10s vs. the original ~1h52m per-subject baseline (~6.9x faster), byte-comparable output
- Known, accepted (not fixed) risk: concurrent `.reload()` calls share one Flywheel client/HTTP session across worker threads without an SDK-documented guarantee this is safe; observed correct in all testing to date

## v0.0.2

- Pins flywheel-sdk to 22.0.0 to fix deserialization crash caused by missing `Avatars` model in SDK 22.1.0+

## v0.0.1

Initial release.

- Export form data for all subjects in a Flywheel group/project without a participant list
- Config-driven: `group_id`, `project_name`, `modules`, `study_id`
- Optional `formver_split` mode producing one CSV per (module, form version) pair
- Optional `include_derived` to include derived variables
- Resilient processing: logs warnings for individual subject failures, continues with remaining subjects
