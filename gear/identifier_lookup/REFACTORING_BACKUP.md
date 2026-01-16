# Identifier Lookup Refactoring Backup Documentation

## Current Implementation Backup

This document serves as a backup reference for the current NACCIDLookupVisitor implementation before refactoring.

### Original NACCIDLookupVisitor Responsibilities

The current `NACCIDLookupVisitor` class has the following mixed responsibilities:

1. **Identifier Lookup**:
   - Validates CSV headers for required fields
   - Looks up NACCIDs from PTIDs using identifier repository
   - Transforms CSV rows by adding NACCID and MODULE fields
   - Writes transformed rows to output CSV

2. **QC Status Logging** (to be separated):
   - Creates QC status logs for each visit using QCStatusLogManager
   - Updates QC metadata with PASS/FAIL status
   - Handles QC logging errors and stores them in misc_errors
   - Resets QC metadata with "ALL" flag for first gear in pipeline

### Current Constructor Parameters

```python
def __init__(
    self,
    *,
    adcid: int,
    identifiers: Dict[str, IdentifierObject],
    output_file: TextIO,
    module_name: str,
    module_configs: ModuleConfigs,
    error_writer: ListErrorWriter,
    gear_name: str,
    misc_errors: List[FileError],
    project: Optional[ProjectAdaptor] = None,
) -> None:
```

### QC Logging Setup (to be removed)

The current implementation sets up QC logging in the constructor:

```python
# Setup QC status log manager
errorlog_template = (
    module_configs.errorlog_template
    if module_configs.errorlog_template
    else ErrorLogTemplate(
        id_field=FieldNames.PTID, date_field=module_configs.date_field
    )
)
visit_annotator = FileVisitAnnotator(project) if project else None
self.__qc_log_manager = (
    QCStatusLogManager(errorlog_template, visit_annotator)
    if visit_annotator
    else None
)
```

### QC Logging in visit_row (to be removed)

The current `visit_row` method includes QC logging calls:

```python
def visit_row(self, row: Dict[str, Any], line_num: int) -> bool:
    # ... identifier lookup logic ...
    
    # QC logging calls (to be removed):
    if not self.__validator.check(row=row, line_number=line_num):
        self.__update_visit_error_log(input_record=row, qc_passed=False)
        return False
    
    # ... more identifier lookup ...
    
    if not identifier:
        # ... error handling ...
        self.__update_visit_error_log(input_record=row, qc_passed=False)
        return False
    
    # ... CSV transformation ...
    
    if not self.__update_visit_error_log(input_record=row, qc_passed=True):
        return False
```

### __update_visit_error_log Method (to be removed)

This entire method handles QC logging and should be moved to QCStatusLogCSVVisitor:

```python
def __update_visit_error_log(
    self, *, input_record: Dict[str, Any], qc_passed: bool
) -> bool:
    # QC logging implementation using QCStatusLogManager
    # This logic will be moved to QCStatusLogCSVVisitor
```

### Expected Behavior After Refactoring

After refactoring, the system should:

1. Produce identical output CSV files
2. Generate the same error messages and error file structure  
3. Maintain the same QC log file naming and metadata structure
4. Preserve the same QC metadata reset behavior (reset_qc_metadata="ALL")
5. Handle miscellaneous errors in the same manner

### Test Coverage Requirements

The refactored implementation must pass all existing tests and maintain backward compatibility for:

- Empty input streams
- Missing headers
- Missing ID columns
- Data with matching identifiers
- Data with mismatched identifiers
- Error handling and reporting
- QC status log creation and updates

## Backup Created

Date: $(date)
Branch: backup/add-event-logging-before-refactoring
Original Implementation: gear/identifier_lookup/src/python/identifier_app/main.py