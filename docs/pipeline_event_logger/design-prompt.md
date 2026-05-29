# Pipeline Event Logger Gear

## Goal

Build an independent Flywheel gear that handles QC status logging and event capture for pipeline gears that follow the Flywheel QC metadata conventions (`context.metadata.add_qc_result`) but don't have NACC logging built in.

This is needed for the imaging pipeline, where preexisting Flywheel gears process files and write QC results to file metadata, but don't know about NACC's project-level QC status logs or S3 event capture.

## What it should do

1. Run after an upstream gear completes on a file
2. Read the upstream gear's QC outcome from the file's custom info (`file.info.qc.{gear_name}`)
3. Update (or create) the project-level QC status log for that visit/file, attributing the entry to the upstream gear
4. Optionally capture a `VisitEvent` to the S3 transaction log

## Key decisions already made

- **Gear name attribution**: The QC log entry should be attributed to the upstream gear name, not to this gear. Downstream systems that read the QC log use the gear name.
- **Single upstream gear**: The gear handles one upstream gear per invocation. The upstream gear name is a config parameter that resolves which section of `file.info.qc` to read.
- **Event action is configured**: The event action (`"submit"`, `"pass-qc"`, etc.) is an explicit config parameter. The gear does not infer the action from the QC status.
- **Timestamp**: Use `file.info.validated-timestamp` if the upstream gear set it, fall back to `file.modified`.

## Existing infrastructure to use

- `QCStatusLogManager` and `FileVisitAnnotator` in `common/src/python/error_logging/` for QC log management
- `create_visit_event()` in `common/src/python/event_capture/event_generator.py` for building events from project context
- `VisitEventCapture` in `common/src/python/event_capture/event_capture.py` for S3 event logging
- `DataIdentification` in `nacc-common` for visit/file identification
- `FileQCModel` in `nacc-common` for reading QC metadata from file.info

## Context for DataIdentification

The gear reads `DataIdentification` from `file.info.data_identification` on the input file. Upstream gears (or earlier pipeline stages) are responsible for writing this metadata as a flat dict with keys: `ptid`, `adcid`, `date`, `module`/`modality`, `visitnum`.

This means the gear cannot be used directly with form pipelines that only write `file.info.visit` or `file.info.forms.json` — those pipelines would need to be updated to also write `file.info.data_identification`.

See `image_identifier_lookup` gear for the imaging pattern.

## Reference gears

- `gear/image_identifier_lookup/` — Similar logging pattern (QC log + event capture), imaging-specific
- `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py` — Form-specific event capture
- `gear/form_qc_checker/` and `gear/image_identifier_lookup/` — Examples of gears using `context.metadata.add_qc_result` and `context.metadata.update_file_metadata`
