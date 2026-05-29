# Requirements Document

## Introduction

The `image_identifier_lookup` gear builds a `DataIdentification` object during its workflow but currently does not persist it to the input file's metadata. Downstream gears — specifically `pipeline_event_logger` — expect to find `file.info.data_identification` on the input file so they can attribute QC log entries and events to the correct visit/file without reconstructing the identification from subject metadata and DICOM data.

This feature adds a step to write the serialized `DataIdentification` to `file.info.data_identification` after the gear completes its processing, enabling the imaging pipeline to use `pipeline_event_logger`.

## Glossary

- **Image_Identifier_Lookup_Gear**: The Flywheel gear that resolves NACCID identifiers and builds `DataIdentification` from project metadata, subject labels, and DICOM tags. Implemented across `run.py` (gear interface) and `main.py` (business logic).
- **Pipeline_Event_Logger_Gear**: A downstream Flywheel gear that reads `file.info.data_identification` to attribute QC log entries and capture visit events for upstream gears.
- **DataIdentification**: A Pydantic model (`nacc_common.data_identification.DataIdentification`) that composes participant, visit, and data-type identification into a single object. Supports flat serialization via `model_dump()` and reconstruction via `from_visit_metadata()`.
- **File_Metadata**: The `file.info` dictionary on a Flywheel file entry, used to store QC results, timestamps, gear tags, and identification data.
- **Serialized_DataIdentification**: A flat dictionary produced by `DataIdentification.model_dump()` containing keys such as `ptid`, `adcid`, `naccid`, `date`, `modality`, and `visitnum`. This is the format written to `file.info.data_identification`.
- **ImageIdentifierLookup**: The orchestrator class in `main.py` that executes the identifier lookup workflow and returns processing results.
- **ImageIdentifierLookupVisitor**: The gear execution visitor in `run.py` that manages Flywheel context, invokes `ImageIdentifierLookup.run()`, and writes file metadata.
- **LookupContext**: A Pydantic model that accumulates data needed for the identifier lookup workflow, including the `visit_metadata` field which holds the built `DataIdentification`.

## Requirements

### Requirement 1: Return DataIdentification from Orchestrator

**User Story:** As a gear developer, I want `ImageIdentifierLookup.run()` to return the built `DataIdentification` alongside the existing success and errors tuple, so that `run.py` can write it to file metadata.

#### Acceptance Criteria

1. THE ImageIdentifierLookup `run()` method SHALL return a tuple of `(bool, FileErrorList, Optional[DataIdentification])`.
2. WHEN `DataIdentification` is successfully built from visit metadata, THE ImageIdentifierLookup `run()` method SHALL include the DataIdentification object as the third element of the returned tuple.
3. WHEN visit metadata is unavailable (PTID or study_date is missing), THE ImageIdentifierLookup `run()` method SHALL return `None` as the third element of the returned tuple.

### Requirement 2: Write Serialized DataIdentification to File Metadata

**User Story:** As a pipeline operator, I want the `image_identifier_lookup` gear to write the `DataIdentification` to `file.info.data_identification`, so that downstream gears can read visit/file identification directly from the file.

#### Acceptance Criteria

1. WHEN `ImageIdentifierLookup.run()` returns a non-None `DataIdentification`, THE ImageIdentifierLookupVisitor SHALL write the Serialized_DataIdentification to `file.info.data_identification` using `context.metadata.update_file_metadata`.
2. THE ImageIdentifierLookupVisitor SHALL serialize the DataIdentification using `model_dump()` to produce a flat dictionary before writing to File_Metadata.
3. WHEN `ImageIdentifierLookup.run()` returns `None` for `DataIdentification`, THE ImageIdentifierLookupVisitor SHALL skip writing `data_identification` to File_Metadata.
4. THE ImageIdentifierLookupVisitor SHALL write `data_identification` to File_Metadata after writing QC results, the validated timestamp, and gear tags.

### Requirement 3: Serialization Round-Trip Compatibility

**User Story:** As a developer of the `pipeline_event_logger` gear, I want the serialized `DataIdentification` written by `image_identifier_lookup` to be reconstructable via `DataIdentification.from_visit_metadata()`, so that downstream gears can reliably deserialize it.

#### Acceptance Criteria

1. FOR ALL valid DataIdentification objects built by the Image_Identifier_Lookup_Gear, THE Serialized_DataIdentification produced by `model_dump()` SHALL be accepted by `DataIdentification.from_visit_metadata()` as keyword arguments without error.
2. FOR ALL valid DataIdentification objects built by the Image_Identifier_Lookup_Gear, parsing the Serialized_DataIdentification via `from_visit_metadata(**serialized)` then serializing again via `model_dump()` SHALL produce a dictionary equal to the original Serialized_DataIdentification (round-trip property).
3. THE Serialized_DataIdentification SHALL contain the keys `ptid`, `adcid`, `date`, `modality`, and `visitnum` matching the fields expected by `DataIdentification.from_visit_metadata()`.

### Requirement 4: Preserve Existing File Metadata Behavior

**User Story:** As a pipeline operator, I want the existing file metadata updates (QC result, validated timestamp, gear tags) to remain unchanged after this modification, so that no existing functionality is broken.

#### Acceptance Criteria

1. THE ImageIdentifierLookupVisitor SHALL continue to write QC results (PASS/FAIL validation state and error data) to File_Metadata as before.
2. THE ImageIdentifierLookupVisitor SHALL continue to write the validated timestamp to `file.info.validated-timestamp` as before.
3. THE ImageIdentifierLookupVisitor SHALL continue to update gear tags on the file as before.
4. THE ImageIdentifierLookupVisitor SHALL write `data_identification` as an additional metadata update without modifying the existing metadata update calls.

### Requirement 5: Metadata Write Failure Handling

**User Story:** As a pipeline operator, I want the gear to handle failures when writing `data_identification` to file metadata gracefully, so that a metadata write failure does not cause the entire gear run to fail.

#### Acceptance Criteria

1. IF writing `data_identification` to File_Metadata fails, THEN THE ImageIdentifierLookupVisitor SHALL log the error.
2. IF writing `data_identification` to File_Metadata fails, THEN THE ImageIdentifierLookupVisitor SHALL continue gear execution without raising an exception, consistent with how other metadata write failures are handled in `_update_file_metadata`.

### Requirement 6: Dry Run Behavior

**User Story:** As a gear developer, I want the `data_identification` write to respect the dry run configuration, so that no metadata is written during test runs.

#### Acceptance Criteria

1. WHILE the gear is running in dry run mode, THE ImageIdentifierLookupVisitor SHALL skip writing `data_identification` to File_Metadata.
2. WHILE the gear is running in dry run mode, THE ImageIdentifierLookup `run()` method SHALL still return the built DataIdentification in the tuple (dry run only affects metadata writes in `run.py`).
