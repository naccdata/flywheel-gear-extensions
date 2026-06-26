# Visit Metadata Refactoring - Implementation Summary

## Overview

This spec documents the refactoring of visit metadata architecture and QC status log filename management. The work was completed through vibe coding sessions and has been fully implemented and tested.

## What Was Accomplished

### 1. Core Architecture Refactoring

**DataIdentification Model** (`nacc-common/src/python/nacc_common/data_identification.py`) - New structured model for visit metadata:

- `ParticipantIdentification` - Participant and center identification (adcid, ptid, naccid)
- `VisitIdentification` - Visit-specific information (visitnum)
- `FormIdentification` - Form-specific fields (module, packet)
- `ImageIdentification` - Image-specific fields (modality)
- `DataIdentification` - Composite class combining all components
- `AbstractIdentificationVisitor` - Visitor pattern interface for traversing identification structure

**Factory Methods:**

- `from_form_record()` - Creates DataIdentification from CSV record
- `from_visit_metadata()` - Creates DataIdentification from flat dictionary (backward compatibility)

**Benefits:**

- Type safety through Pydantic validation
- Clear separation of concerns
- Extensible for future datatypes through visitor pattern
- Backward compatible through type aliases (VisitKeys = DataIdentification, VisitMetadata = DataIdentification)

### 2. Enhanced QC Log Filenames

**ErrorLogTemplate Changes** (`common/src/python/error_logging/error_logger.py`):

**New Format:**

```
{ptid}[_{visitnum}]_{date}_{module}[_{packet}]_qc-status.log
```

**Implementation:**

- `ErrorLogIdentificationVisitor` - Visitor that traverses DataIdentification structure to extract fields
  - `log_name_prefix` property - Returns prefix with all available fields (visitnum, packet included)
  - `legacy_log_name_prefix` property - Returns prefix without visitnum/packet for backward compatibility
- `ErrorLogTemplate.instantiate(data_id)` - Generates new format filename using visitor pattern
- `ErrorLogTemplate.instantiate_legacy(data_id)` - Generates legacy format filename
- Removed `VisitLabelTemplate` base class (no longer needed)

**Examples:**

- Form with all fields: `12345_001_2024-01-15_a1_i_qc-status.log`
- Form without visitnum: `12345_2024-01-15_np_i_qc-status.log`
- Legacy format: `12345_2024-01-15_a1_qc-status.log`
- Image data: `12345_2024-01-20_mr_qc-status.log`

### 3. Centralized QC Log Management

**QCStatusLogManager** (`common/src/python/error_logging/qc_status_log_creator.py`) - Single point of control for QC log operations:

- `update_qc_log()` - Creates or updates QC status logs using DataIdentification
- `get_qc_log_filename()` - Finds existing files in both new and legacy formats
  - Tries `instantiate()` first (new format)
  - Falls back to `instantiate_legacy()` (legacy format)
  - Returns new format filename if neither exists (what would be created)
- Handles both new and legacy filename formats transparently
- Returns filename on success for downstream use

**FileVisitAnnotator** - Annotates QC log files with visit metadata:

- `annotate_qc_log_file()` - Adds visit metadata to file.info.visit

### 4. Production Code Migration

All gears migrated to use `QCStatusLogManager` and `DataIdentification`:

**Gears:**

- `gear/form_qc_checker` - Uses `DataIdentification.from_form_record()` and `QCStatusLogManager`
- `gear/form_qc_coordinator` - Uses `DataIdentification.from_visit_metadata()` and `QCStatusLogManager`
- `gear/form_transformer` - Uses `DataIdentification.from_visit_metadata()` for both update and lookup
- `gear/identifier_provisioning` - Uses `DataIdentification.from_visit_metadata()` and `QCStatusLogManager`
- `gear/participant_transfer` - Uses `DataIdentification.from_visit_metadata()` and `QCStatusLogManager`

**Common Libraries:**

- `common/src/python/event_capture/event_processor.py` - Uses `ErrorLogTemplate.instantiate()`
- `gear/form_scheduler` - `EventAccumulator` uses `ErrorLogTemplate.instantiate()`

### 5. Code Cleanup

- Removed `VisitLabelTemplate` base class (only used for inheritance, no longer needed)
- Removed unused `id_field` and `date_field` parameters from 4 `ErrorLogTemplate()` initializations:
  - `gear/form_qc_checker/src/python/form_qc_app/processor.py`
  - `gear/form_transformer/src/python/form_csv_app/main.py`
  - `gear/identifier_provisioning/src/python/identifier_provisioning_app/main.py`
  - `gear/participant_transfer/src/python/participant_transfer_app/transfer.py`

### 6. Test Updates

**New Tests:**

- `common/test/python/error_logging/test_error_log_identification_visitor.py` - Tests for visitor pattern
- `common/test/python/error_logging/test_error_log_template_data_identification.py` - Tests for new filename methods
- `common/test/python/error_logging/test_qc_filename_creation.py` - Tests for QC filename creation

**Updated Tests:**

- `gear/form_transformer/test/python/test_uds_transform.py` - Updated to use DataIdentification
- `common/test/python/outputs/test_project_report_visitor.py` - Updated to use DataIdentification
- `gear/form_scheduler/test/python/test_property_qc_status_matching.py` - Updated for new API
- Multiple property-based tests updated for DataIdentification structure

## Key Design Decisions

### Visitor Pattern for Filename Generation

Instead of hardcoding field extraction logic, we use the visitor pattern:

- `ErrorLogIdentificationVisitor` implements `AbstractIdentificationVisitor`
- Traverses `DataIdentification` structure via `accept()` method
- Each component type (participant, visit, form, image) has its own `visit_*()` method
- Visitor collects fields and builds filename prefix in correct order
- Two prefix methods:
  - `log_name_prefix` - Includes all fields (visitnum, packet)
  - `legacy_log_name_prefix` - Excludes visitnum and packet
- Extensible: new datatypes just add new visit methods without changing core logic

### Backward Compatibility Strategy

- Type aliases in `nacc_common.error_models`: `VisitKeys = DataIdentification`, `VisitMetadata = DataIdentification`
- `ErrorLogTemplate.instantiate()` generates new format with all available fields
- `ErrorLogTemplate.instantiate_legacy()` generates legacy format (no visitnum/packet)
- `QCStatusLogManager.get_qc_log_filename()` tries both formats:
  1. Check if new format file exists
  2. Check if legacy format file exists
  3. Return new format (what would be created)
- Existing files with legacy names continue to work

### Centralized Management

- `QCStatusLogManager` encapsulates all QC log operations
- Gears use `update_qc_log()` instead of calling `update_error_log_and_qc_metadata()` directly
- Gears use `get_qc_log_filename()` for lookups instead of generating filenames themselves
- Consistent behavior across all gears
- Easier to maintain and extend

## Testing

All tests pass (`pants test ::`):

- Unit tests for component classes (ParticipantIdentification, VisitIdentification, etc.)
- Unit tests for visitor pattern (ErrorLogIdentificationVisitor)
- Integration tests for QC log operations (QCStatusLogManager)
- Property-based tests for event structure compatibility
- Property-based tests for visit metadata validation
- Backward compatibility tests for legacy filenames
- Tests for both new and legacy filename formats

## Documentation

### Spec Files

- `requirements.md` - Updated with actual implementation details
- `design.md` - Updated with visitor pattern and actual method names
- `tasks.md` - Marked all tasks as complete

### Archive

Working documents from vibe sessions moved to `archive/`:

- `completion-summary.md` - Original completion summary
- `qc-filename-exploration.md` - Filename format exploration
- `instantiate-usage-inventory.md` - Usage inventory
- `errorlogtemplate-arguments-analysis.md` - Arguments analysis
- `instantiate-analysis.md` - Method usage analysis

## Status

✅ **Complete** - All implementation, testing, and documentation tasks are finished.

## Files Changed (vs main branch)

**Core Libraries:**

- `nacc-common/src/python/nacc_common/data_identification.py` - NEW: DataIdentification model and visitor pattern
- `nacc-common/src/python/nacc_common/error_models.py` - Updated: Type aliases for backward compatibility
- `common/src/python/error_logging/error_logger.py` - Updated: Visitor pattern, instantiate() methods
- `common/src/python/error_logging/qc_status_log_creator.py` - Updated: QCStatusLogManager methods
- `common/src/python/event_capture/visit_events.py` - Updated: VisitEvent uses DataIdentification
- `common/src/python/configs/ingest_configs.py` - Updated: Removed VisitLabelTemplate

**Gears (5 gears updated):**

- `gear/form_qc_checker/src/python/form_qc_app/processor.py`
- `gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py`
- `gear/form_transformer/src/python/form_csv_app/main.py`
- `gear/identifier_provisioning/src/python/identifier_provisioning_app/main.py`
- `gear/participant_transfer/src/python/participant_transfer_app/transfer.py`
- `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py`

**Tests (30+ test files updated):**

- New test files for visitor pattern and DataIdentification
- Updated property-based tests for new structure
- Updated integration tests for QC logging

**Total Changes:** 67 files changed, 5120 insertions(+), 1239 deletions(-)

## References

- DataIdentification: `nacc-common/src/python/nacc_common/data_identification.py`
- Visitor Pattern: `common/src/python/error_logging/error_logger.py` (ErrorLogIdentificationVisitor)
- QC Manager: `common/src/python/error_logging/qc_status_log_creator.py`
- Event Capture: `common/src/python/event_capture/visit_events.py`
