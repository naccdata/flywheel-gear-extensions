# Refactor: Write DataIdentification to file.info

## Goal

Modify the `image_identifier_lookup` gear to write the serialized `DataIdentification` to `file.info.data_identification` on the input file after building it. This enables downstream gears (specifically `pipeline_event_logger`) to read visit/file identification directly from the file without needing to reconstruct it from subject metadata and DICOM data.

## Background

Currently, the `image_identifier_lookup` gear:
1. Builds a `DataIdentification` from project metadata (adcid), subject label (ptid), and DICOM tags (study_date, modality)
2. Uses it internally for QC status log updates and event capture
3. Writes NACCID and DICOM metadata to `subject.info`
4. Writes QC result, validated-timestamp, and gear tags to `file.info`
5. Does NOT write the `DataIdentification` to `file.info`

The `pipeline_event_logger` gear expects to find `file.info.data_identification` on the input file so it can attribute QC log entries and events to the correct visit/file. Without this, the pipeline event logger cannot operate on files processed by the imaging pipeline.

## What to Change

In `run.py`'s `_update_file_metadata` method, add a step to write the serialized `DataIdentification` to `file.info.data_identification`.

### Current flow in run.py

```
_update_file_metadata():
  1. add_qc_result (validation state + errors)
  2. update_file_metadata (validated-timestamp)
  3. update_file_metadata (gear tags)
```

### Proposed flow

```
_update_file_metadata():
  1. add_qc_result (validation state + errors)
  2. update_file_metadata (validated-timestamp)
  3. update_file_metadata (gear tags)
  4. update_file_metadata (data_identification)   ← NEW
```

### Implementation Details

The `DataIdentification` is built in `main.py` via `_build_data_identification()` and is available after `ImageIdentifierLookup.run()` returns. It needs to be passed back to `run.py` so it can be written to file metadata.

**Option A**: Return `DataIdentification` from `ImageIdentifierLookup.run()` alongside the existing `(success, errors)` tuple.

Current signature:
```python
def run(self) -> tuple[bool, FileErrorList]:
```

New signature:
```python
def run(self) -> tuple[bool, FileErrorList, Optional[DataIdentification]]:
```

**Option B**: Accept a callback or output sink that `main.py` writes to.

Option A is simpler and consistent with how the gear already returns results to `run.py`.

### Serialization Format

`DataIdentification` should be serialized as a flat dict matching what `DataIdentification.from_visit_metadata()` accepts as kwargs:

```python
data_identification.model_dump()
```

This produces a nested structure. For the pipeline_event_logger to reconstruct it via `from_visit_metadata(**dict)`, we need the flat form:

```python
{
    "ptid": "ABC123",
    "adcid": 42,
    "naccid": "NACC000123",
    "date": "2024-06-15",
    "modality": "MR",
    "visitnum": None
}
```

Check how `DataIdentification.from_visit_metadata()` and `DataIdentification.to_visit_metadata()` relate — use whichever serialization the `from_visit_metadata` factory can round-trip.

### Where to Write

```python
context.metadata.update_file_metadata(
    self.__file_input.file_input,
    container_type=context.config.destination["type"],
    info={"data_identification": serialized_data_id},
)
```

### When NOT to Write

If `DataIdentification` is `None` (e.g., visit metadata couldn't be built because PTID or study_date was missing), skip writing `data_identification`. The pipeline_event_logger will raise an error when it can't find it, which is the correct behavior — if we can't identify the visit, downstream logging shouldn't proceed.

## Testing

- Verify `file.info.data_identification` is written when `DataIdentification` is successfully built
- Verify `file.info.data_identification` is NOT written when `DataIdentification` is None
- Verify the serialized dict can be round-tripped through `DataIdentification.from_visit_metadata()`
- Verify existing tests still pass (QC result, timestamp, tags unchanged)

## Dependencies

- This change is a prerequisite for using `pipeline_event_logger` in the imaging pipeline
- No changes needed in `nacc-common` or `common/`
- The `pipeline_event_logger` gear already reads from `file.info.data_identification`
