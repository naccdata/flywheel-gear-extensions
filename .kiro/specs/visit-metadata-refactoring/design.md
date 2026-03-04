# Design Document: Visit Metadata Architecture Refactoring

## Overview

This document describes the design for refactoring the visit metadata architecture in the nacc-common and common packages. The refactoring separates concerns between participant identification, visit association, and datatype-specific metadata using composition while maintaining backward compatibility through type aliases.

## Design Principles

1. **Composition Over Inheritance**: Use composition to combine identification components rather than deep inheritance hierarchies
2. **Separation of Concerns**: Participant identification, visit association, and datatype-specific fields are separate components
3. **Backward Compatibility**: Type aliases maintain the existing public API for external users
4. **Flat Serialization**: Composed structure serializes to flat format for compatibility with existing storage and APIs

## Architecture

### Component Classes

#### ParticipantIdentification

Identifies a participant and their center.

```python
class ParticipantIdentification(BaseModel):
    adcid: Optional[int] = None
    ptid: Optional[str] = None
    naccid: Optional[str] = None
```

**Factory Methods:**
- `from_form_record(record)` - Creates from form data dictionary

#### VisitIdentification

Identifies a specific visit.

```python
class VisitIdentification(BaseModel):
    visitnum: Optional[str] = None
```

**Factory Methods:**
- `from_form_record(record)` - Creates from form data dictionary

**Validation:**
- Converts empty string to None for visitnum

#### FormIdentification

Identifies form-specific data.

```python
class FormIdentification(BaseModel):
    module: Optional[str] = None  # Form name (A1, B1, NP, Milestone, etc.)
    packet: Optional[str] = None  # I=Initial, F=Followup, T=Telephone
```

**Factory Methods:**
- `from_form_record(record)` - Creates from form data dictionary

**Validation:**
- Normalizes module and packet to uppercase
- Converts empty string to None for packet
- Raises EmptyFieldError if module is None

#### ImageIdentification

Identifies image-specific data.

```python
class ImageIdentification(BaseModel):
    modality: Optional[str] = None  # Imaging modality (MR, CT, PET, etc.)
```

### Composite Class

#### DataIdentification

Base class for all data identification using composition.

```python
class DataIdentification(BaseModel):
    participant: ParticipantIdentification
    date: Optional[str] = None
    visit: Optional[VisitIdentification] = None
    data: Optional[FormIdentification | ImageIdentification] = None
```

**Factory Methods:**
- `from_visit_metadata(**kwargs)` - Creates from flat visit metadata fields (backward compatibility)
- `from_form_record(record, date_field)` - Creates from form data record with date validation
- `from_form_record_safe(record, date_field)` - Safe version that returns None on error
- `from_visit_info(file_entry)` - Creates from FileEntry.info.visit

**Instance Methods:**
- `with_updates(adcid, packet, visitnum)` - Returns copy with specified fields updated
- `__getattr__(name)` - Delegates attribute access to composed components for flat access pattern

**Serialization:**
- `serialize_model()` - Flattens composed structure to flat dictionary for backward compatibility

**Output Format:**
```python
{
    "adcid": 1,
    "ptid": "12345",
    "naccid": "NACC123",
    "visitnum": "001",
    "date": "2024-01-15",
    "module": "A1",
    "packet": "I"
}
```

### Type Aliases for Backward Compatibility

```python
# In nacc_common/error_models.py
VisitKeys = DataIdentification
VisitMetadata = DataIdentification
```

These aliases allow existing code using `VisitKeys` or `VisitMetadata` to continue working without modification.

## Event Capture Integration

### VisitEvent

The `VisitEvent` class has been updated to use `DataIdentification` with composition.

```python
class VisitEvent(BaseModel):
    action: VisitEventType
    study: str = "adrc"
    project_label: str
    center_label: str
    gear_name: str
    data_identification: DataIdentification
    datatype: DatatypeNameType
    timestamp: datetime
```

**Backward Compatibility:**
- `__getattr__()` exposes fields from data_identification (ptid, naccid, adcid, visitnum, date, module, packet, modality)
- Supports aliases: pipeline_adcid (→ adcid), visit_date (→ date), visit_number (→ visitnum)

**Serialization:**
- `serialize_model()` flattens data_identification and maps field names:
  - adcid → pipeline_adcid
  - date → visit_date
  - visitnum → visit_number
  - ptid, naccid, module, packet pass through unchanged

**Validation:**
- `validate_datatype_consistency()` ensures datatype field matches data_identification.data type:
  - datatype="form" requires FormIdentification with non-None module
  - datatype="dicom" requires ImageIdentification with non-None modality

## Enhanced QC Status Log Filenames

### Overview

QC status log filenames have been enhanced to include visitnum and packet fields when available, providing richer information while maintaining backward compatibility with legacy filenames.

### Filename Format

**New Format:**
```
{ptid}[_{visitnum}]_{date}_{module}[_{packet}]_qc-status.log
```

Where `[_{field}]` means "include if non-None"

The filename includes all non-None fields from DataIdentification:
- `ptid` - participant ID (required)
- `visitnum` - visit number (optional, included if present)
- `date` - date (required)
- `module` - module/modality (required)
- `packet` - packet type (optional, datatype-specific field for forms)

**Form Examples:**

Form with visitnum and packet:
```
ptid=12345, visitnum=001, date=2024-01-15, module=a1, packet=i
→ 12345_001_2024-01-15_a1_i_qc-status.log
```

Form with packet but no visitnum (non-visit form):
```
ptid=12345, visitnum=None, date=2024-01-15, module=np, packet=i
→ 12345_2024-01-15_np_i_qc-status.log
```

Form with visitnum but no packet:
```
ptid=12345, visitnum=001, date=2024-01-15, module=a1, packet=None
→ 12345_001_2024-01-15_a1_qc-status.log
```

Legacy form format (no visitnum or packet):
```
ptid=12345, visitnum=None, date=2024-01-15, module=a1, packet=None
→ 12345_2024-01-15_a1_qc-status.log
```

**Image Examples:**

Image data (no packet field, packet is form-specific):
```
ptid=12345, visitnum=None, date=2024-01-20, module=mr, packet=None
→ 12345_2024-01-20_mr_qc-status.log
```

Image with visitnum:
```
ptid=12345, visitnum=001, date=2024-01-20, module=ct, packet=None
→ 12345_001_2024-01-20_ct_qc-status.log
```

**Future Datatype Examples:**

The format is extensible to future datatypes. For example, if genomic data is added with an assay_type field:

Genomic data (hypothetical):
```
ptid=12345, visitnum=None, date=2024-03-10, module=wgs, assay_type=None
→ 12345_2024-03-10_wgs_qc-status.log
```

If future datatypes add new identification fields to DataIdentification, those fields can be included in the filename format by extending the `instantiate_from_data_identification()` method. The current format handles common fields (ptid, visitnum, date, module) and datatype-specific fields (packet for forms).

### ErrorLogTemplate Methods

#### instantiate()

Generates filename directly from DataIdentification using a visitor pattern:

```python
def instantiate(
    self, 
    data_id: DataIdentification
) -> Optional[str]:
    """Generate QC log filename from DataIdentification.
    
    Uses ErrorLogIdentificationVisitor to extract fields and build filename.
    Returns None if required fields are missing.
    """
```

**Behavior:**
- Uses visitor pattern to traverse DataIdentification structure
- Visitor extracts non-None values from participant, visit, and data components
- Normalizes field values (lowercase, leading zeros for visitnum)
- Builds filename by joining extracted fields with underscores
- Works for any datatype because visitor handles different identification types

**Implementation:**
```python
visitor = ErrorLogIdentificationVisitor()
data_id.accept(visitor)
prefix = visitor.log_name_prefix()
if prefix:
    return self.create_filename(prefix)
return None
```

#### instantiate_legacy()

Generates legacy format filename (without visitnum/packet) for backward compatibility:

```python
def instantiate_legacy(
    self, 
    data_id: DataIdentification
) -> Optional[str]:
    """Generate legacy format QC log filename from DataIdentification.
    
    Uses ErrorLogIdentificationVisitor to extract fields but excludes
    visitnum and packet for backward compatibility with old filenames.
    Returns None if required fields are missing.
    """
```

**Behavior:**
- Uses same visitor pattern as `instantiate()`
- Calls `visitor.legacy_log_name_prefix()` instead of `log_name_prefix()`
- Excludes visitnum and packet fields
- Returns legacy format: `{ptid}_{date}_{module}_qc-status.log`

### Design Approach

The filename generation uses a **visitor pattern** that is datatype-agnostic:

**Visitor Pattern:**

The `ErrorLogIdentificationVisitor` traverses the DataIdentification structure:
```python
class ErrorLogIdentificationVisitor(AbstractIdentificationVisitor):
    def visit_participant(self, participant: ParticipantIdentification) -> None:
        # Extract ptid
        
    def visit_visit(self, visit: VisitIdentification) -> None:
        # Extract visitnum
        
    def visit_form(self, form: FormIdentification) -> None:
        # Extract module and packet
        
    def visit_image(self, image: ImageIdentification) -> None:
        # Extract modality (as module)
```

**How It Works:**

1. **Visitor traverses structure** - DataIdentification.accept() calls visitor methods
2. **Extract available fields** - Each visit method extracts relevant fields
3. **Include non-None fields** - Only fields that are non-None are included
4. **Build prefix** - Visitor assembles fields in correct order
5. **Extensible** - New datatypes add new visit methods without changing core logic

**Field Order:**
- `ptid` (from participant)
- `visitnum` (from visit, if present)
- `date` (from data_id)
- `module` (from form or image)
- `packet` (from form, if present)

**Example:**
```python
# Form data with all fields
data_id = DataIdentification(ptid="12345", visitnum="001", date="2024-01-15", 
                              module="a1", packet="i")
visitor = ErrorLogIdentificationVisitor()
data_id.accept(visitor)
# visitor.log_name_prefix() → "12345_001_2024-01-15_a1_i"
# Result: "12345_001_2024-01-15_a1_i_qc-status.log"

# Image data (no packet field)
data_id = DataIdentification(ptid="12345", visitnum=None, date="2024-01-20", 
                              module="mr", packet=None)
visitor = ErrorLogIdentificationVisitor()
data_id.accept(visitor)
# visitor.log_name_prefix() → "12345_2024-01-20_mr"
# Result: "12345_2024-01-20_mr_qc-status.log"
```

The implementation determines field presence by visiting the DataIdentification structure, not by checking datatype labels.

### Backward Compatibility Strategy

**For file creation:**
- Use `instantiate()` to generate new format
- New files include all available fields (visitnum, packet when present)

**For file lookup:**
- `QCStatusLogManager.get_qc_log_filename()` tries both formats
- Try new format first with `instantiate()`
- Fall back to legacy format with `instantiate_legacy()`
- Existing files with legacy names are still found

### Integration Points

The new methods have been integrated into:

1. **QCStatusLogManager** - Uses `instantiate()` for file creation and `get_qc_log_filename()` for file lookup (tries both new and legacy formats)
2. **EventAccumulator** (form_scheduler) - Uses `instantiate()` for QC log filename generation
3. **EventProcessor** (event_capture) - Uses `instantiate()` for QC log filename generation
4. **All gears** - Migrated to use `QCStatusLogManager` for centralized QC log operations

### Benefits

1. **Richer information** - Filenames include visitnum and packet when available
2. **Conceptual clarity** - Filename structure matches DataIdentification model
3. **Backward compatible** - Old filenames still work, lookup tries multiple formats
4. **No collisions** - Still unique within project scope (each project is scoped to one center)
5. **Extensible** - Easy to add new fields for future datatypes

## Data Flow

### Form Processing

```
CSV Record
  ↓
DataIdentification.from_form_record(record, date_field)
  ↓
DataIdentification {
  participant: ParticipantIdentification(adcid, ptid, naccid)
  date: "2024-01-15"
  visit: VisitIdentification(visitnum)
  data: FormIdentification(module, packet)
}
  ↓
model_dump() → Flat dictionary
  ↓
Stored in file.info.visit or used for VisitEvent
```

### QC Logging

```
DataIdentification
  ↓
ErrorLogTemplate.instantiate(data_id)
  ↓
ErrorLogIdentificationVisitor traverses structure
  ↓
QC log filename: {ptid}[_{visitnum}]_{date}_{module}[_{packet}]_qc-status.log

For file lookup (backward compatibility):
QCStatusLogManager.get_qc_log_filename(data_id, project)
  ↓
Try ErrorLogTemplate.instantiate(data_id) → check if file exists
  ↓
Try ErrorLogTemplate.instantiate_legacy(data_id) → check if file exists
  ↓
Return new format filename (what would be created)
```

### Event Capture

```
DataIdentification
  ↓
VisitEvent(
  action="submit",
  data_identification=data_identification,
  datatype="form",
  ...
)
  ↓
model_dump() → {
  action, study, project_label, center_label, gear_name,
  pipeline_adcid, ptid, naccid, visit_number, visit_date,
  module, packet, datatype, timestamp
}
  ↓
JSON event file
```

## Migration Strategy

### Phase 1: Implementation (Completed)

- ✅ Added component classes (ParticipantIdentification, VisitIdentification, FormIdentification, ImageIdentification)
- ✅ Added composite class (DataIdentification)
- ✅ Added type aliases (VisitKeys, VisitMetadata)
- ✅ Updated VisitEvent to use DataIdentification
- ✅ Implemented flat serialization for backward compatibility
- ✅ Added enhanced QC filename methods to ErrorLogTemplate
- ✅ Implemented `instantiate()` method using visitor pattern
- ✅ Implemented `instantiate_legacy()` method for backward compatibility
- ✅ Implemented `ErrorLogIdentificationVisitor` for datatype-agnostic filename generation

### Phase 2: QC Filename Integration (Completed)

- ✅ Updated QCStatusLogManager to use `instantiate()` for file creation
- ✅ Updated QCStatusLogManager.get_qc_log_filename() to try both new and legacy formats
- ✅ Updated EventAccumulator in form_scheduler to use `instantiate()`
- ✅ Updated EventProcessor in event_capture to use `instantiate()`
- ✅ Migrated all gears to use QCStatusLogManager
- ✅ Verified backward compatibility with legacy filenames
- ✅ Verified new filenames include visitnum and packet when available
- ✅ Removed unused `id_field` and `date_field` parameters from ErrorLogTemplate initializations

### Phase 3: Internal Migration (Future)

- Update internal code (common/, gear/) to use DataIdentification directly
- Use component extraction methods where beneficial
- Maintain backward compatibility through type aliases

### Phase 4: Documentation (Future)

- Update all documentation to reference DataIdentification
- Add migration guide for external users
- Mark old names as deprecated in docstrings

### Phase 5: Cleanup (Future Major Version)

- Remove type aliases
- Remove deprecated names
- Breaking change with clear migration path

## External Visibility and Compatibility

The data identification models have three main external touchpoints:

### 1. QC Status Log Filenames

**Format:** `{ptid}[_{visitnum}]_{date}_{module}[_{packet}]_qc-status.log`

**Generated by:** `ErrorLogTemplate.instantiate_from_data_identification()`

**Visibility:** File names in Flywheel project files

**Impact of Changes:**
- Filename format now includes visitnum and packet when available
- Legacy format still supported for backward compatibility
- File lookup tries multiple formats in priority order
- `module` field is used directly in filename
- For forms: module = form name (A1, B1, NP)
- For images: module = modality (MR, CT, PET)
- Different datatypes can coexist with same naming pattern

**Examples:**
- With visitnum and packet: `12345_001_2024-01-15_a1_i_qc-status.log`
- With packet only: `12345_2024-01-15_np_i_qc-status.log`
- With visitnum only: `12345_001_2024-01-15_a1_qc-status.log`
- Legacy format (no visitnum or packet): `12345_2024-01-15_a1_qc-status.log`
- Image data (no packet support): `12345_2024-01-20_mr_qc-status.log`

**Compatibility:** ✅ Backward compatible - legacy filenames still found via `get_possible_filenames()`

### 2. File Metadata (file.info.visit)

**Format:** JSON stored in `file.info.visit` on QC status log files

**Example:**
```json
{
  "visit": {
    "adcid": 1,
    "ptid": "12345",
    "visitnum": "001",
    "date": "2024-01-15",
    "module": "A1",
    "packet": "I",
    "naccid": "NACC123"
  }
}
```

**Generated by:** `FileVisitAnnotator.annotate_qc_log_file()`

**Visibility:** Stored in Flywheel, read by event capture and other gears

**Impact of Changes:**
- JSON structure must remain stable for existing files
- Field names must not change
- New fields can be added (backward compatible)
- Missing fields should be handled gracefully

**Compatibility:** ✅ No changes needed - serialization format preserved via `model_dump()`

### 3. Transactional Events (VisitEvent JSON)

**Format:** JSON files that become Parquet tables

**Example:**
```json
{
  "action": "submit",
  "study": "adrc",
  "adcid": 1,
  "ptid": "12345",
  "visit_number": "001",
  "visit_date": "2024-01-15",
  "module": "A1",
  "packet": "I",
  "naccid": "NACC123"
}
```

**Generated by:** `VisitMetadata.model_dump()` with field name mapping (date → visit_date, visitnum → visit_number)

**Visibility:** 
- JSON files in Flywheel
- Parquet tables for analytics
- Potentially consumed by external systems

**Impact of Changes:**
- JSON schema must remain stable
- Field names must not change (visit_date, visit_number, module, packet)
- Different datatypes could have different event schemas
- Parquet table schemas must remain compatible

**Compatibility:** ✅ No changes needed - field mapping preserved via `model_serializer`

## Backward Compatibility

### What Remains Unchanged

1. **Serialization Format**: JSON/dict output is identical to legacy format
2. **QC Log Filenames**: Format remains `{ptid}_{date}_{module}_qc-status.log`
3. **File Metadata**: `file.info.visit` structure unchanged
4. **Event JSON**: Field names and structure unchanged (pipeline_adcid, visit_date, visit_number, etc.)
5. **Public API**: External users see no changes via type aliases

### What Changes Internally

1. **Class Names**: DataIdentification instead of VisitKeys (via type alias)
2. **Internal Structure**: Composition instead of flat fields
3. **Factory Methods**: New names (from_form_record, from_visit_info) but old behavior preserved
4. **Component Access**: Can extract components (participant, visit, data) when needed

## Extensibility

### Adding New Datatypes

To add a new datatype (e.g., genomic data):

1. Create identification class:
```python
class GenomicIdentification(BaseModel):
    assay_type: Optional[str] = None
    sample_id: Optional[str] = None
```

2. Add to DataIdentification.data union:
```python
data: Optional[FormIdentification | ImageIdentification | GenomicIdentification] = None
```

3. Update VisitEvent validation for new datatype:
```python
elif self.datatype == "genomic":
    if not isinstance(data_obj, GenomicIdentification):
        raise ValueError(...)
```

4. No changes needed to QC logging or base infrastructure

## Testing Strategy

### Unit Tests

- Test component classes independently (ParticipantIdentification, VisitIdentification, FormIdentification, ImageIdentification)
- Test DataIdentification factory methods
- Test serialization produces correct flat format
- Test __getattr__ delegation
- Test with_updates() method

### Integration Tests

- Test QC logging with DataIdentification
- Test event capture with VisitEvent
- Test file annotation with file.info.visit
- Test backward compatibility with type aliases

### Property-Based Tests

- Test serialization/deserialization round-trips
- Test that flat and composed representations are equivalent
- Test field name mapping consistency

## Open Questions

None - implementation is complete and working.

## References

- Requirements Document: `.kiro/specs/visit-metadata-refactoring/requirements.md`
- Implementation: `nacc-common/src/python/nacc_common/data_identification.py`
- Event Capture: `common/src/python/event_capture/visit_events.py`
