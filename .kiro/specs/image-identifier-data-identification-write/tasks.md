# Implementation Plan: Write DataIdentification to File Metadata

## Overview

Modify the `image_identifier_lookup` gear to persist the `DataIdentification` object to `file.info.data_identification` after processing. The change extends the `ImageIdentifierLookup.run()` return tuple in `main.py` and adds a metadata write step in `run.py`'s `_update_file_metadata()`.

## Tasks

- [x] 1. Extend `ImageIdentifierLookup.run()` return type to include DataIdentification
  - [x] 1.1 Modify `run()` in `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/main.py` to return `tuple[bool, FileErrorList, Optional[DataIdentification]]`
    - Change the return type annotation from `tuple[bool, FileErrorList]` to `tuple[bool, FileErrorList, Optional[DataIdentification]]`
    - Include the `data_identification` local variable (already built by `_build_data_identification()`) as the third element of the returned tuple
    - When `_build_data_identification()` returns `None` (visit metadata unavailable), the third element is `None`
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Write unit tests for the updated `run()` return value
    - Add tests in `gear/image_identifier_lookup/test/python/image_identifier_lookup_test/test_visitor_and_main.py`
    - Test that `run()` returns a 3-tuple with `DataIdentification` when visit metadata is available
    - Test that `run()` returns `None` as third element when visit metadata is unavailable (no PTID or study_date)
    - Test that the returned `DataIdentification` matches the one built from the lookup context
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Update `run.py` to unpack the new return value and write DataIdentification to file metadata
  - [x] 2.1 Update the call site in `ImageIdentifierLookupVisitor.run()` to unpack the 3-tuple
    - In `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/run.py`, change `success, errors = ImageIdentifierLookup(...).run()` to `success, errors, data_identification = ImageIdentifierLookup(...).run()`
    - Pass `data_identification` to `_update_file_metadata()` as a new keyword argument
    - _Requirements: 2.1, 2.3_

  - [x] 2.2 Add `data_identification` parameter and write logic to `_update_file_metadata()`
    - Add `data_identification: Optional[DataIdentification] = None` parameter to `_update_file_metadata()`
    - Add the `DataIdentification` import from `nacc_common.data_identification`
    - After the existing gear tags write, add a new block that:
      - Checks if `data_identification` is not `None`
      - Serializes via `data_identification.model_dump()`
      - Writes to `file.info.data_identification` using `context.metadata.update_file_metadata(self.__file_input.file_input, container_type=context.config.destination["type"], info={"data_identification": serialized})`
    - Wrap the new write in the existing `FlywheelError` exception handler so failures are logged but do not fail the gear
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

  - [x] 2.3 Write unit tests for the metadata write behavior
    - Add tests in `gear/image_identifier_lookup/test/python/image_identifier_lookup_test/test_visitor_and_main.py`
    - Test that `_update_file_metadata` calls `update_file_metadata` with `data_identification` dict when `DataIdentification` is provided
    - Test that `_update_file_metadata` does NOT call `update_file_metadata` for `data_identification` when `DataIdentification` is `None`
    - Test that the `data_identification` write occurs after QC result, timestamp, and gear tags writes (verify call order)
    - Test that existing QC result, timestamp, and tag writes are unchanged when `data_identification` is provided
    - Test that a `FlywheelError` during the `data_identification` write is logged but does not raise
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2_

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Handle dry run behavior for DataIdentification write
  - [x] 4.1 Verify dry run skips the `data_identification` metadata write
    - The existing dry run guard in `run.py` already skips `_update_file_metadata` entirely when `self.__dry_run` is `True` — verify this covers the new write
    - If the dry run check is not at the `_update_file_metadata` call level, add a guard so `data_identification` is not written in dry run mode
    - Confirm that `ImageIdentifierLookup.run()` still returns the built `DataIdentification` in dry run mode (dry run only affects metadata writes in `run.py`)
    - _Requirements: 6.1, 6.2_

  - [x] 4.2 Write unit tests for dry run behavior
    - Test that `data_identification` is NOT written to file metadata when `dry_run=True`
    - Test that `ImageIdentifierLookup.run()` still returns a non-None `DataIdentification` when `dry_run=True` and visit metadata is available
    - _Requirements: 6.1, 6.2_

- [x] 5. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The design does not include a Correctness Properties section, so no property-based tests are included
- The implementation language is Python, matching the existing codebase
- Test files are located at `gear/image_identifier_lookup/test/python/image_identifier_lookup_test/`
- Source files are at `gear/image_identifier_lookup/src/python/image_identifier_lookup_app/`
