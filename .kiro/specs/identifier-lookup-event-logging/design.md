# Design Document

## Overview

This design document outlines the addition of submission event logging to the identifier lookup gear. The implementation will add a CSVLoggingVisitor to the existing AggregateCSVVisitor pattern, creating submit events for each visit when processing CSV files in the "nacc" direction with QC status log management enabled. Event logging will only occur when QC logging is also active, ensuring that submit events are only created for properly tracked visits. This follows the same pattern used in the submission_logger gear and leverages the recently refactored visitor architecture.

## Architecture

The enhanced architecture extends the existing AggregateCSVVisitor pattern by adding event logging:

```
AggregateCSVVisitor (nacc direction only)
├── NACCIDLookupVisitor (identifier lookup)
├── QCStatusLogCSVVisitor (QC logging)
└── CSVLoggingVisitor (event logging) [NEW]
```

### Current Architecture

The identifier lookup gear currently uses:
- NACCIDLookupVisitor for identifier lookup and CSV transformation
- QCStatusLogCSVVisitor for QC status log creation
- AggregateCSVVisitor to coordinate both visitors

### Proposed Enhancement

Add CSVLoggingVisitor as a third visitor in the aggregate for "nacc" direction processing when QC logging is enabled:
- Reuse existing CSVLoggingVisitor from common library
- Configure with action="submit" and datatype="form"
- Integrate into existing AggregateCSVVisitor coordination
- Only add when form_configs_file is provided (same condition as QC logging)

### Benefits

- Consolidates submission tracking into identifier lookup gear
- Enables eventual removal of submission_logger gear
- Follows established visitor pattern
- Minimal code changes required
- Maintains backward compatibility
- Event logging only occurs when QC logging is active, ensuring consistency

## Components and Interfaces

### 1. VisitEventLogger (Reused)

**Responsibilities:**
- Write visit events to S3 bucket
- Generate event filenames with proper structure
- Handle event serialization

**Usage:**
- Create instance with S3BucketInterface and environment
- Pass to CSVLoggingVisitor for event logging

**Interface:**
```python
class VisitEventLogger:
    def __init__(
        self,
        s3_bucket: S3BucketInterface,
        environment: str = "prod"
    ) -> None:
        # Initialize with S3 bucket and environment
    
    def log_event(self, event: VisitEvent) -> None:
        # Log a visit event to S3
```

### 2. CSVLoggingVisitor (Reused)

**Responsibilities:**
- Extract visit information from CSV rows
- Create VisitEvent objects with submit action
- Log events using VisitEventLogger
- Handle missing fields gracefully

**Usage:**
- Reuse existing implementation from `common/src/python/event_logging/csv_logging_visitor.py`
- Configure with center label, project label, gear name, and module configs
- Add as third visitor in AggregateCSVVisitor
- Note: CSVLoggingVisitor already extracts packet field from CSV rows and includes it in VisitEvent

**Interface:**
```python
class CSVLoggingVisitor(CSVVisitor):
    def __init__(
        self,
        center_label: str,
        project_label: str,
        gear_name: str,
        event_logger: VisitEventLogger,
        module_configs: ModuleConfigs,
        error_writer: ListErrorWriter,
        timestamp: datetime,
        action: VisitEventType = "submit",
        datatype: DatatypeNameType = "form",
    ) -> None:
        # Initialize event logging visitor
    
    def visit_header(self, header: List[str]) -> bool:
        # Validate required fields present
    
    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        # Extract visit info and log event
```

### 3. Enhanced IdentifierLookupVisitor

**Key Changes:**
- Add VisitEventLogger initialization in `create()` method
- Modify `__build_naccid_lookup()` to include CSVLoggingVisitor
- Add configuration parameters for event bucket and environment
- Handle S3 bucket initialization errors

**New Configuration Parameters:**
- `environment`: Environment for event logging (default: "prod")
- `event_bucket`: S3 bucket name for events (default: "nacc-event-logs")

## Data Models

### Configuration

```python
@dataclass
class EventLoggingConfig:
    """Configuration for event logging."""
    environment: str = "prod"
    event_bucket: str = "nacc-event-logs"
    enabled: bool = True  # Only enabled for "nacc" direction
```

### Visitor Coordination

The visitors will coordinate through:
1. **Shared Error Writer**: All visitors use the same ListErrorWriter instance
2. **Visit All Strategy**: AggregateCSVVisitor uses visit_all_strategy to ensure all visitors process each row
3. **Independent Failures**: Event logging failures don't affect identifier lookup or QC logging

## Error Handling

### Error Coordination Strategy

1. **Event Logging Errors**: Handled gracefully by CSVLoggingVisitor, don't fail overall processing
2. **Missing Fields**: CSVLoggingVisitor skips rows with missing required fields
3. **S3 Bucket Errors**: Fail early during initialization if bucket not accessible
4. **Success Determination**: Overall success based on identifier lookup, not event logging

### Error Flow

```
Initialization
├── Create S3BucketInterface
│   └── Fail if bucket not accessible
├── Create VisitEventLogger
└── Create CSVLoggingVisitor

Row Processing (nacc direction)
├── NACCIDLookupVisitor.visit_row()
│   ├── Perform identifier lookup
│   └── Record errors if any
├── QCStatusLogCSVVisitor.visit_row()
│   ├── Create QC status log
│   └── Handle QC errors gracefully
└── CSVLoggingVisitor.visit_row()
    ├── Extract visit information
    ├── Log submit event
    └── Handle event logging errors gracefully
```

## Testing Strategy

### Unit Testing Approach

**CSVLoggingVisitor Integration Tests:**
- Test event logging with valid visit data
- Test graceful handling of missing fields
- Test event logging failures don't affect other visitors

**AggregateCSVVisitor Coordination Tests:**
- Test three-visitor coordination (identifier lookup, QC logging, event logging)
- Test visitor independence (failures in one don't affect others)
- Test visit_all_strategy ensures all visitors process each row

**Direction-Specific Tests:**
- Test event logging only occurs in "nacc" direction
- Test "center" direction maintains existing behavior

### Property-Based Testing

Property-based tests will be implemented using pytest-hypothesis to verify correctness properties across many inputs.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


## Property Reflection

After analyzing all acceptance criteria, several properties can be consolidated to eliminate redundancy:

- Properties 1.1 and 1.2 are redundant - both test that valid rows create events
- Properties 1.4 and 6.1 are redundant - both test that "center" direction doesn't create events
- Properties 3.1 and 3.2 are redundant - both test visitor composition
- Properties 3.5 and 6.5 are redundant - both test success determination
- Properties 2.2, 2.4, and 2.5 can be combined into a single property about event metadata correctness
- Requirement 5 criteria are meta-requirements about testing, not functional requirements
- Property 6.3 is already covered by existing refactoring tests

### Core Properties

**Property 1: Submit Event Creation**
*For any* CSV file processed in "nacc" direction with QC status log management enabled and valid visit rows, the system should create a submit event for each valid visit row
**Validates: Requirements 1.1, 1.2**

**Property 2: Missing Field Resilience**
*For any* CSV row missing required visit fields, the system should skip event logging for that row and continue processing without failure
**Validates: Requirements 1.3**

**Property 3: Direction-Specific Event Logging**
*For any* CSV file processed in "center" direction or without QC status log management, the system should not create any submit events
**Validates: Requirements 1.4, 3.3, 6.1**

**Property 4: Event Logging Resilience**
*For any* event logging failure during visit processing, the system should continue processing subsequent visits without failing the entire operation
**Validates: Requirements 1.5**

**Property 5: Event Metadata Correctness**
*For any* submit event created, the event should contain correct center label, project label, gear name, file creation timestamp, datatype="form", and packet value if present in the CSV row
**Validates: Requirements 2.2, 2.4, 2.5, 2.6**

**Property 6: Visitor Independence**
*For any* failure in one visitor (identifier lookup, QC logging, or event logging), the other visitors should continue processing without being affected
**Validates: Requirements 3.4**

**Property 7: Success Determination**
*For any* CSV file processing, the overall success status should be determined by identifier lookup results, not event logging results
**Validates: Requirements 3.5, 6.5**

**Property 8: Output Format Preservation**
*For any* CSV file processed, the output file format and QC metadata structure should remain identical to the format before event logging was added
**Validates: Requirements 6.4**

**Property 9: Error Reporting Preservation**
*For any* identifier lookup failure, the error reporting behavior should remain identical to the behavior before event logging was added
**Validates: Requirements 6.2**

## Implementation Notes

### Configuration Changes

Add two new configuration parameters to the identifier lookup gear manifest:
- `environment`: String, default "prod", options ["prod", "dev"]
- `event_bucket`: String, default "nacc-event-logs"

### Code Changes

1. **IdentifierLookupVisitor.create()**
   - Add S3BucketInterface initialization
   - Add VisitEventLogger initialization
   - Handle S3 bucket access errors

2. **IdentifierLookupVisitor.__build_naccid_lookup()**
   - Create CSVLoggingVisitor instance (only called when form_configs_file is provided)
   - Add to AggregateCSVVisitor visitors list alongside QC visitor
   - Ensure visit_all_strategy is used

3. **IdentifierLookupVisitor.run()**
   - Extract file creation timestamp
   - Pass timestamp to __build_naccid_lookup()

### Dependencies

No new dependencies required - all components already exist in the common library:
- `event_logging.csv_logging_visitor.CSVLoggingVisitor`
- `event_logging.event_logger.VisitEventLogger`
- `s3.s3_bucket.S3BucketInterface`

## Migration Path

This change is additive and maintains full backward compatibility:
1. Event logging only activates for "nacc" direction with QC logging enabled (form_configs_file provided)
2. Existing output files and QC metadata unchanged
3. Success/failure determination unchanged
4. Error reporting unchanged
5. "center" direction processing unchanged
6. Processing without form_configs_file unchanged

The submission_logger gear can be deprecated after this change is deployed and validated.
