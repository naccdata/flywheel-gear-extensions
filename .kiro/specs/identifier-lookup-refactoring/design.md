# Design Document

## Overview

This design document outlines the refactoring of the identifier lookup gear to separate concerns between identifier lookup functionality and QC status log creation. The refactoring will split the current monolithic NACCIDLookupVisitor into focused, single-responsibility components using the established AggregateCSVVisitor pattern.

## Architecture

The refactored architecture follows the Composite pattern using AggregateCSVVisitor to coordinate multiple specialized visitors:

```
AggregateCSVVisitor
├── NACCIDLookupVisitor (simplified)
└── QCStatusLogCSVVisitor (reused from common)
```

### Current Architecture Issues

- NACCIDLookupVisitor has mixed responsibilities (identifier lookup + QC logging)
- Tight coupling between identifier lookup and QC logging logic
- Difficult to test identifier lookup independently
- QC logging logic is not reusable across gears

### Proposed Architecture Benefits

- Single Responsibility Principle: Each visitor has one clear purpose
- Loose coupling between identifier lookup and QC logging
- Improved testability and maintainability
- Reusable QC logging component
- Consistent with submission_logger gear pattern

## Components and Interfaces

### 1. Simplified NACCIDLookupVisitor

**Responsibilities:**
- Validate CSV headers for required identifier fields
- Look up NACCIDs from PTIDs using identifier repository
- Transform CSV rows by adding NACCID and MODULE fields
- Write transformed rows to output CSV
- Report identifier lookup errors

**Key Changes:**
- Remove QC logging logic (`__update_visit_error_log` method)
- Remove QC-related dependencies (QCStatusLogManager, project adaptor)
- Simplify constructor parameters
- Focus solely on CSV transformation

**Interface:**
```python
class NACCIDLookupVisitor(CSVVisitor):
    def __init__(
        self,
        *,
        adcid: int,
        identifiers: Dict[str, IdentifierObject],
        output_file: TextIO,
        module_name: str,
        module_configs: ModuleConfigs,
        error_writer: ListErrorWriter,
        misc_errors: List[FileError],
    ) -> None:
        # Removed: gear_name, project parameters
        # Removed: QC logging setup
    
    def visit_header(self, header: List[str]) -> bool:
        # Validate required fields for identifier lookup
    
    def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
        # Perform identifier lookup and CSV transformation
        # No QC logging calls
```

### 2. QCStatusLogCSVVisitor (Reused)

**Responsibilities:**
- Extract visit information from CSV rows
- Create QC status logs for each visit
- Update QC metadata based on processing results
- Handle QC logging errors gracefully

**Usage:**
- Reuse existing implementation from `common/src/python/error_logging/qc_status_log_csv_visitor.py`
- Configure with appropriate module configs and QC log manager
- Coordinate with identifier lookup results for status determination

### 3. AggregateCSVVisitor (Reused)

**Responsibilities:**
- Coordinate execution of multiple visitors
- Ensure proper error handling across visitors
- Maintain processing order and dependencies

**Usage:**
- Reuse existing implementation from `common/src/python/inputs/csv_reader.py`
- No changes needed to the AggregateCSVVisitor class itself
- Simply instantiate with the two specialized visitors

**Error Coordination Strategy:**
- Use shared error writer for consistent error reporting
- Leverage existing visitor coordination logic
- Handle partial failures through existing mechanisms

## Data Models

### Visit Processing State

```python
@dataclass
class VisitProcessingResult:
    """Tracks the result of processing a single visit."""
    visit_keys: VisitKeys
    identifier_lookup_success: bool
    identifier_lookup_errors: List[FileError]
    qc_log_success: bool
    line_number: int
```

### Visitor Communication

The visitors will communicate through:
1. **Shared Error Writer**: Both visitors use the same ListErrorWriter instance
2. **Row State**: Each visitor processes the same row data
3. **Visit Keys**: Consistent visit identification across visitors

## Error Handling

### Error Coordination Strategy

1. **Identifier Lookup Errors**: Recorded by NACCIDLookupVisitor in shared error writer
2. **QC Status Determination**: QCStatusLogCSVVisitor reads error writer state to determine PASS/FAIL
3. **Error Writer Lifecycle**: Clear errors at start of each row, accumulate during processing
4. **Miscellaneous Errors**: Collected in shared list for gear-level reporting

### Error Flow

```
Row Processing Start
├── Clear error writer
├── NACCIDLookupVisitor.visit_row()
│   ├── Validate row data
│   ├── Perform identifier lookup
│   └── Record errors if any
├── QCStatusLogCSVVisitor.visit_row()
│   ├── Extract visit keys
│   ├── Check error writer for failures
│   ├── Create QC log with appropriate status
│   └── Handle QC logging errors
└── Row Processing Complete
```

## Testing Strategy

### Unit Testing Approach

**NACCIDLookupVisitor Tests:**
- Test identifier lookup functionality in isolation
- Verify CSV transformation without QC dependencies
- Test error handling for missing identifiers
- Validate header processing and field requirements

**QCStatusLogCSVVisitor Tests:**
- Test QC log creation with various visit data
- Verify error status determination
- Test graceful handling of QC logging failures

**AggregateCSVVisitor Integration Tests:**
- Test coordination between visitors using existing AggregateCSVVisitor
- Verify error propagation and handling through existing mechanisms
- Test backward compatibility scenarios

### Property-Based Testing

Property-based tests will be implemented using pytest-hypothesis to verify correctness properties across many inputs.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing all acceptance criteria, several properties can be consolidated to eliminate redundancy:

- Properties 1.1, 1.2, 1.3 can be combined into a single property about NACCIDLookupVisitor separation of concerns
- Properties 2.2 and 2.3 can be combined into a single property about QC status determination
- Properties 4.1, 4.2, 4.3 can be combined into a comprehensive backward compatibility property
- Properties 5.1 and 5.2 can be combined into a single coordination property

### Core Properties

**Property 1: NACCIDLookupVisitor Separation of Concerns**
*For any* CSV row processing, the NACCIDLookupVisitor should perform identifier lookup and CSV transformation without directly creating QC logs or updating QC metadata
**Validates: Requirements 1.1, 1.2, 1.3**

**Property 2: QC Status Determination**
*For any* visit processing result, the QC visitor should create logs with PASS status for successful identifier lookups and FAIL status with error details for failed lookups
**Validates: Requirements 2.2, 2.3**

**Property 3: QC Logging Resilience**
*For any* QC log creation failure, the system should continue processing subsequent visits without failing the entire operation
**Validates: Requirements 2.4**

**Property 4: Aggregate Visitor Coordination**
*For any* CSV file processing, the AggregateCSVVisitor should execute both identifier lookup and QC logging visitors for each row and ensure all visitors validate headers successfully
**Validates: Requirements 3.2, 3.3**

**Property 5: Error Propagation**
*For any* visitor failure within the aggregate, the system should report the failure appropriately while maintaining correct processing order
**Validates: Requirements 3.4, 3.5**

**Property 6: Backward Compatibility**
*For any* input CSV file, the refactored system should produce identical output files, error messages, and QC log structures compared to the original implementation
**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

**Property 7: Visitor Coordination**
*For any* visit processing, both visitors should have consistent access to visit information and coordinate error reporting without duplication
**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

**Property 8: Visitor Isolation**
*For any* error occurring in one visitor, the system should handle the failure gracefully without corrupting the other visitor's state
**Validates: Requirements 5.5**

**Property 9: Visit Key Consistency**
*For any* CSV row containing visit data, the system should use VisitKeys to identify visits consistently across all visitors
**Validates: Requirements 2.5**

**Property 10: QC Visitor Usage**
*For any* CSV processing requiring QC logging, the system should use QCStatusLogCSVVisitor to create visit-specific QC status logs
**Validates: Requirements 2.1**