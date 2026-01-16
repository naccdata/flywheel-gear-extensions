# Design Document

## Overview

This design document outlines the refactoring of event logging in the form scheduler gear to simplify and correct the current implementation. The refactor removes complex event accumulation logic and focuses solely on logging QC-pass events for JSON files at the acquisition level. The current implementation incorrectly logs both submit events (now handled by identifier lookup) and processes files at both project and acquisition levels based on false assumptions.

The refactored solution will:
- Only log QC-pass events (no submit or QC-fail events)
- Only process JSON files at acquisition level (ignore CSV files at project level)
- Leverage visit details added to QC status files by identifier lookup
- Simplify the EventAccumulator class by removing complex visitor patterns
- Maintain backward compatibility with event consumers

## Architecture

### Current Architecture Issues

The current form scheduler event logging has several problems:
1. **Dual responsibility**: Logs both submit events and QC outcome events
2. **Wrong scope**: Processes both project-level CSV files and acquisition-level JSON files
3. **Complex visitor patterns**: Uses multiple visitor classes for error accumulation
4. **Duplicate prevention**: Maintains complex logic to prevent duplicate submit events
5. **Over-engineering**: Handles multiple event types when only QC-pass events are needed

### Proposed Simplified Architecture

```
FormSchedulerQueue
├── _log_pipeline_events() [SIMPLIFIED]
│   └── EventAccumulator [REFACTORED]
│       ├── Only processes acquisition-level JSON files
│       ├── Only logs QC-pass events
│       ├── Uses visit details from QC status custom info
│       └── Falls back to JSON file metadata if needed
└── _process_pipeline_queue() [UNCHANGED]
    └── Calls _log_pipeline_events() after pipeline completion
```

### Key Simplifications

1. **Single Event Type**: Only QC-pass events (action="pass-qc")
2. **Use Existing Queue**: Process JSON files already in finalization queue
3. **Match to QC Logs**: Find corresponding QC status logs at project level
4. **Single Metadata Source**: QC status files with fallback to JSON metadata
5. **No Complex Visitor Pattern**: Direct processing without error accumulation visitor traversal
6. **No Duplicate Prevention**: Not needed since we don't log submit events

## Components and Interfaces

### 1. Simplified EventAccumulator

**Current Responsibilities (TO BE REMOVED):**
- Log submit events and QC outcome events
- Process both project and acquisition level files
- Complex visitor pattern for error accumulation
- Duplicate submit event prevention
- Handle multiple event types

**New Responsibilities:**
- Log only QC-pass events for JSON files already in finalization queue
- Find corresponding QC status logs at project level for each JSON file
- Extract visit metadata from QC status custom info or JSON file
- Simple, direct processing without complex visitor patterns

**Interface:**
```python
class EventAccumulator:
    """Simplified event accumulator for QC-pass events only."""
    
    def __init__(
        self,
        event_logger: VisitEventLogger,
        datatype: DatatypeNameType = "form"
    ) -> None:
        # Simplified constructor - no pipeline needed
    
    def log_events(
        self, 
        json_file: FileEntry,  # JSON file from finalization queue
        project: ProjectAdaptor
    ) -> None:
        # Find corresponding QC status log and log QC-pass event if passed
```

### 2. Visit Metadata Extraction

**Primary Source: QC Status Custom Info with VisitMetadata**
The `FileVisitAnnotator` (used by identifier lookup) will be updated to add visit metadata to QC status files using the new `VisitMetadata` Pydantic model that extends `VisitKeys`. Only fields needed for VisitEvent creation are included:

```python
# Expected structure in qc-status file custom info
{
    "visit": {
        "ptid": "110001",
        "visitnum": "01", 
        "date": "2024-01-15",
        "module": "UDS",
        "packet": "I"  # New field from VisitMetadata extension
        # Note: adcid comes from project.get_pipeline_adcid()
        # Note: naccid not needed for VisitEvent creation
    }
}
```

**Fallback Source: JSON File Metadata**
If custom info is not available, extract from JSON file's forms.json metadata and create VisitMetadata. Both sources have the same information needed for VisitEvent:

```python
# Expected structure in JSON file.info.forms.json
{
    "ptid": "110001",
    "visitnum": "01",
    "visitdate": "2024-01-15",  # Maps to VisitMetadata.date
    "packet": "I",
    "module": "UDS"
}
```

### 3. File Discovery and Filtering

**Current Approach (TO BE REMOVED):**
- Uses `ProjectReportVisitor` to scan ALL QC status logs at project level
- Processes both CSV and JSON file QC status logs
- Complex visitor pattern for error accumulation

**New Approach:**
- Use `ErrorLogTemplate` to generate QC status log filename from JSON file metadata
- Look up the QC status log file by name in project files
- Only process QC status logs that correspond to JSON files in the finalization queue
- Simple, direct processing without complex visitor patterns

**Key Insight:**
The finalization pipeline already has the JSON files from acquisitions in the queue. We can use `ErrorLogTemplate` with the JSON file's forms.json metadata to generate the expected QC status log filename, then look it up directly in the project files.

**Implementation:**
```python
def find_qc_status_for_json_file(
    self,
    json_file: FileEntry,
    project: ProjectAdaptor,
    error_log_template: ErrorLogTemplate
) -> Optional[FileEntry]:
    """Find the QC status log for a JSON file at project level.
    
    Uses ErrorLogTemplate to generate the expected QC status log filename
    from the JSON file's forms.json metadata, then looks it up in project files.
    
    Args:
        json_file: The JSON file from acquisition (already in queue)
        project: The project containing QC status logs
        error_log_template: Template for generating QC status log filenames
        
    Returns:
        The corresponding QC status log file, or None if not found
    """
    # Extract visit metadata from JSON file
    forms_json = json_file.info.get('forms', {}).get('json', {})
    if not forms_json:
        return None
    
    # Get module from forms metadata
    module = forms_json.get('module')
    if not module:
        return None
    
    # Use ErrorLogTemplate to generate expected QC status log filename
    qc_log_name = error_log_template.instantiate(record=forms_json, module=module)
    if not qc_log_name:
        return None
    
    # Look up the QC status log file by name in project files
    qc_log_file = project.get_file(qc_log_name)
    return qc_log_file
```

## Data Models

### Leverage Existing Models

**Use Existing VisitEvent Model:**
The existing `VisitEvent` Pydantic model already supports QC-pass events and contains all required fields.

**Extend VisitKeys with New Model:**
Create a new `VisitMetadata` model that extends `VisitKeys` to include the packet field needed for complete VisitEvent creation.

**Note on Serialization:**
The `VisitMetadata` model uses a `@model_serializer` decorator for the `to_visit_event_fields` method, which transforms field names when serializing for VisitEvent creation. For QC status log annotation, use `model_dump(exclude_none=True, mode="raw")` to get the raw field names without transformation.

```python
class VisitMetadata(VisitKeys):
    """Extended visit metadata that includes packet information for VisitEvent creation.
    
    Extends VisitKeys with the packet field needed for form events.
    Only includes fields actually needed for VisitEvent creation.
    """
    packet: Optional[str] = None
    
    @model_serializer(mode="wrap")
    def to_visit_event_fields(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> Dict[str, Any]:
        """Extract fields needed for VisitEvent creation with proper field name mapping.
        
        Returns:
            Dictionary with fields mapped to VisitEvent field names
        """
        # Use model_dump and map field names for VisitEvent
        data = handler(self)
        if info.mode == "raw":
            return data
            
        data["visit_date"] = data.pop("date")  # VisitKeys.date -> VisitEvent.visit_date
        data["visit_number"] = data.pop("visitnum")  # VisitKeys.visitnum -> VisitEvent.visit_number
        
        return data
```

### Visit Metadata Extraction Utilities

```python
class VisitMetadataExtractor:
    """Utility for extracting VisitMetadata from QC status or JSON files."""
    
    @staticmethod
    def from_qc_status_custom_info(custom_info: dict) -> Optional[VisitMetadata]:
        """Extract VisitMetadata from QC status custom info.
        
        Args:
            custom_info: Custom info from QC status log file
            
        Returns:
            VisitMetadata instance or None if not found/invalid
        """
        visit_data = custom_info.get('visit')
        if not visit_data:
            return None
            
        try:
            # Pydantic will automatically ignore extra fields
            return VisitMetadata.model_validate(visit_data)
        except ValidationError:
            return None
    
    @staticmethod
    def from_json_file_metadata(json_file: FileEntry) -> Optional[VisitMetadata]:
        """Extract VisitMetadata from JSON file forms metadata.
        
        Args:
            json_file: JSON file with forms metadata
            
        Returns:
            VisitMetadata instance or None if not found/invalid
        """
        forms_json = json_file.info.get('forms', {}).get('json', {})
        if not forms_json:
            return None
            
        try:
            # Create mapping for field name differences
            # Pydantic will automatically ignore extra fields
            mapped_data = {**forms_json, 'date': forms_json.get('visitdate')}
            return VisitMetadata.model_validate(mapped_data)
        except ValidationError:
            return None
    
    @staticmethod
    def is_valid_for_event(visit_metadata: VisitMetadata) -> bool:
        """Check if VisitMetadata has required fields for VisitEvent creation."""
        return bool(visit_metadata.ptid and visit_metadata.date and visit_metadata.module)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

After analyzing the acceptance criteria, several properties can be consolidated to eliminate redundancy:

- Properties 1.1 and 1.2 can be combined into a single property about QC-pass event creation
- Properties 1.3 and 1.4 can be combined into a single property about file filtering
- Properties 2.3 and 4.2 are redundant - both test using custom info when available
- Properties 2.4 and 4.3 are redundant - both test JSON fallback
- Properties 4.1 is already covered by the metadata extraction priority property
- Properties 6.1, 6.2, 6.3, 6.4, 6.5 can be combined into event structure compatibility
- Requirements 3 and 7 are meta-requirements about code structure and testing

### Core Properties

**Property 1: QC-Pass Event Creation Only**
*For any* pipeline completion, the system should create QC-pass events only for visits that pass QC validation and should not create any events for visits that fail QC validation
**Validates: Requirements 1.1, 1.2**

**Property 2: JSON File QC Status Processing**
*For any* file processing operation, the system should only examine QC status logs that correspond to JSON files (not CSV files) and should process JSON files that are already in the finalization queue
**Validates: Requirements 1.3, 1.4, 2.1, 2.2**

**Property 3: No Submit Event Creation**
*For any* visit processing, the system should not create submit events since they are handled by the identifier lookup gear
**Validates: Requirements 1.5**

**Property 4: Visit Metadata Extraction Priority**
*For any* QC status log processing, the system should first attempt to extract VisitMetadata from custom info and fall back to JSON file metadata when custom info is not available
**Validates: Requirements 2.3, 2.4, 4.1, 4.2, 4.3**

**Property 5: QC Status Log to JSON File Matching**
*For any* JSON file in the finalization queue, the system should correctly find its corresponding QC status log using ErrorLogTemplate to generate the expected filename
**Validates: Requirements 2.5**

**Property 6: Visit Metadata Validation**
*For any* visit metadata extraction, the system should validate that VisitMetadata contains required fields (ptid, date, module) for VisitEvent creation and skip event logging for visits with incomplete or invalid metadata
**Validates: Requirements 4.4, 4.5**

**Property 7: Error Resilience**
*For any* event logging error (missing files, S3 failures, metadata extraction failures), the system should log warnings and continue pipeline processing without failing
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

**Property 8: Missing Configuration Handling**
*For any* execution where the event logger is not configured, the system should skip event logging entirely without errors
**Validates: Requirements 5.5**

**Property 9: Extended Visit Metadata Model**
*For any* visit metadata annotation or extraction, the system should use the VisitMetadata model that extends VisitKeys with packet information for complete VisitEvent creation
**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

**Property 10: Event Structure Compatibility**
*For any* QC-pass event created, the event should maintain the same structure, field names, S3 storage conventions, timestamp source (QC completion time), required metadata fields, and gear name ("form-scheduler") as the previous implementation
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

## Error Handling

### Simplified Error Handling Strategy

The refactored solution uses a much simpler error handling approach:

1. **File Discovery Errors**: Skip missing or inaccessible files, continue processing
2. **Metadata Extraction Errors**: Skip visits with invalid metadata, continue processing  
3. **Event Creation Errors**: Log warnings, continue processing
4. **S3 Logging Errors**: Log errors, don't retry, continue processing
5. **Configuration Errors**: Skip event logging entirely if logger not configured

### Error Flow

```
Event Logging Process
├── Find acquisition-level QC status logs
│   ├── Skip if file access fails
│   └── Continue with remaining files
├── Extract visit metadata
│   ├── Try custom info first
│   ├── Fall back to JSON metadata
│   ├── Skip if metadata invalid
│   └── Continue with next visit
├── Check QC status
│   ├── Only process if status is PASS
│   └── Skip non-passing visits
├── Create QC-pass event
│   ├── Skip if event creation fails
│   └── Continue with next visit
└── Log event to S3
    ├── Log error if S3 fails
    └── Continue processing (don't retry)
```

## Testing Strategy

### Unit Testing Approach

**Simplified EventAccumulator Tests:**
- Test QC-pass event creation for passing visits
- Test that failing visits don't create events
- Test file filtering (only acquisition-level JSON files)
- Test metadata extraction (custom info and JSON fallback)
- Test error handling (missing files, invalid metadata, S3 failures)

**Integration Tests:**
- Test EventAccumulator integration with FormSchedulerQueue
- Test end-to-end event logging after pipeline completion
- Test backward compatibility with existing event structure

### Property-Based Testing

Property-based tests will be implemented using pytest-hypothesis to verify correctness properties across many inputs.

## Implementation Notes

### Key Changes to EventAccumulator

1. **Remove Complex Visitor Pattern**: Replace visitor-based traversal with direct processing
2. **Remove Submit Event Logic**: Delete all code related to submit event creation
3. **Remove QC-Fail Event Logic**: Delete all code related to not-pass-qc event creation
4. **Remove Duplicate Prevention**: Delete complex tracking of logged submits
5. **Simplify File Discovery**: Replace DataView queries with simple acquisition traversal
6. **Add Custom Info Support**: Add logic to extract visit details from QC status custom info

### Key Changes to FormSchedulerQueue

1. **Simplify _log_pipeline_events()**: Remove complex error handling and visitor coordination
2. **Update EventAccumulator Creation**: Remove pipeline parameter, simplify constructor
3. **Maintain Integration Point**: Keep the same call site after pipeline completion

### Configuration Changes

No configuration changes required - the existing event_bucket parameter is sufficient.

### Dependencies

**Existing Dependencies (Keep):**
- `event_logging.event_logger.VisitEventLogger`
- `flywheel.models.file_entry.FileEntry`
- `flywheel_adaptor.flywheel_proxy.ProjectAdaptor`

**Dependencies to Remove:**
- Complex visitor pattern classes from `nacc_common.qc_report`
- Error accumulation and transformation utilities
- DataView API usage for file discovery

## Migration Path

This refactor maintains backward compatibility for event consumers:

1. **Event Structure**: QC-pass events maintain the same JSON structure and field names
2. **S3 Storage**: Events are stored in the same S3 bucket with same naming conventions
3. **Event Content**: All required metadata fields are preserved
4. **Integration**: FormSchedulerQueue integration point remains unchanged

The main change is the removal of submit events and QC-fail events, which simplifies the event stream for consumers.

## Benefits

1. **Simplified Codebase**: Removes complex visitor patterns and error accumulation logic
2. **Correct Scope**: Only processes relevant files (acquisition-level JSON files)
3. **Single Responsibility**: Only logs QC-pass events, leaving submit events to identifier lookup
4. **Better Performance**: Simpler file discovery and processing logic
5. **Easier Maintenance**: Fewer code paths and simpler error handling
6. **Leverages Existing Work**: Uses visit details added by identifier lookup refactor