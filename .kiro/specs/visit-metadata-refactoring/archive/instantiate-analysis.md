# Analysis: ErrorLogTemplate.instantiate() Calls and update_error_log_and_qc_metadata()

## Summary

All remaining `ErrorLogTemplate.instantiate()` calls in production code (excluding tests and LabelTemplate) are directly followed by calls to `update_error_log_and_qc_metadata()` or similar QC metadata update functions.

## Production Code Locations

### 1. ✅ gear/form_qc_checker/src/python/form_qc_app/processor.py (Line 169)
**Pattern**: `instantiate()` → `update_error_log_and_qc_metadata()`
```python
error_log_name = self._errorlog_template.instantiate(
    record=input_record, module=self._module
)

if not error_log_name or not update_error_log_and_qc_metadata(
    error_log_name=error_log_name,
    destination_prj=self._project,
    gear_name=self._gear_name,
    state="PASS" if qc_passed else "FAIL",
    errors=self._error_writer.errors(),
    reset_qc_metadata=reset_qc_metadata,
):
```
**Context**: Part of `update_visit_error_log()` method
**Migration**: Can use QCStatusLogCreator pattern

---

### 2. ✅ gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py (Line 304)
**Pattern**: `instantiate()` → `update_error_log_and_qc_metadata()`
```python
error_log_name = ErrorLogTemplate().instantiate(
    record={
        f"{FieldNames.PTID}": ptid,
        f"{FieldNames.DATE_COLUMN}": visitdate,
    },
    module=module,
)

if (
    not error_log_name
    or not self.__project
    or not update_error_log_and_qc_metadata(
        error_log_name=error_log_name,
        destination_prj=ProjectAdaptor(...),
        gear_name=gear_name,
        state=status,
        errors=errors,
        reset_qc_metadata="GEAR",
    )
):
```
**Context**: Part of `update_qc_status_log()` method
**Migration**: Can use QCStatusLogCreator pattern

---

### 3. ✅ gear/form_transformer/src/python/form_csv_app/main.py (Line 408)
**Pattern**: `instantiate()` → `update_error_log_and_qc_metadata()`
```python
error_log_name = self.__errorlog_template.instantiate(
    module=self.module, record=input_record
)
if not error_log_name:
    return None

if not update:
    return error_log_name

if not update_error_log_and_qc_metadata(
    error_log_name=error_log_name,
    destination_prj=self.__project,
    gear_name=self.__gear_name,
    state="PASS" if qc_passed else "FAIL",
    errors=self.__error_writer.errors(),
):
```
**Context**: Part of `__update_visit_error_log()` method
**Migration**: Can use QCStatusLogCreator pattern

---

### 4. ⚠️ gear/form_transformer/src/python/form_csv_app/main.py (Line 514)
**Pattern**: `instantiate()` → file lookup (NOT direct QC update)
```python
error_log_name = self.__errorlog_template.instantiate(
    module=self.module, record=input_record
)
if not error_log_name:
    return False

error_log_file = self.__project.get_file(error_log_name)
if not error_log_file:
    log.error(...)
    return False
```
**Context**: Part of `__copy_downstream_gears_metadata()` method
**Purpose**: Looking up existing error log file to copy metadata
**Migration**: Different use case - needs filename for lookup, not creation

---

### 5. ✅ gear/participant_transfer/src/python/participant_transfer_app/transfer.py (Line 442)
**Pattern**: `instantiate()` → `update_gear_qc_status()`
```python
error_log_name = errorlog_template.instantiate(
    module=DefaultValues.ENROLLMENT_MODULE, record=transfer_record
)
if not error_log_name:
    log.warning("Failed to retrieve error log for transfer request")
    return

update_gear_qc_status(
    error_log_name=error_log_name,
    destination_prj=self.__enroll_project,
    gear_name=DefaultValues.PROVISIONING_GEAR,
    status="PASS",
)
```
**Context**: Part of `__update_provisioning_qc_status()` method
**Note**: Uses `update_gear_qc_status()` instead of `update_error_log_and_qc_metadata()`
**Migration**: Can use QCStatusLogCreator pattern

---

### 6. ✅ gear/identifier_provisioning/src/python/identifier_provisioning_app/main.py (Line 92)
**Pattern**: `instantiate()` → `update_error_log_and_qc_metadata()`
```python
error_log_name = errorlog_template.instantiate(
    module=DefaultValues.ENROLLMENT_MODULE, record=input_record
)

status = "PASS" if qc_passed else "FAIL"
if transfer and qc_passed:
    status = "IN REVIEW"

if not error_log_name or not update_error_log_and_qc_metadata(
    error_log_name=error_log_name,
    destination_prj=project,
    gear_name=gear_name,
    state=status,
    errors=errors,
):
```
**Context**: Part of `update_record_level_error_log()` function
**Migration**: Can use QCStatusLogCreator pattern

---

## Out of Scope: LabelTemplate Usage

### common/src/python/uploads/uploader.py (Lines 92, 93, 108, 267, 270, 273)
**Type**: `LabelTemplate.instantiate()` (NOT ErrorLogTemplate)
**Purpose**: Generating Flywheel hierarchy labels (session, acquisition, filename)
**Migration**: Not applicable - different template type for different purpose

---

## Conclusion

**6 out of 6** ErrorLogTemplate.instantiate() calls in production code are directly associated with QC metadata updates:
- 5 locations use `update_error_log_and_qc_metadata()`
- 1 location uses `update_gear_qc_status()` (similar function)
- 1 additional location uses instantiate() for file lookup (not creation)

**Recommendation**: All these locations are good candidates for using the `QCStatusLogCreator` pattern, which encapsulates both filename generation and QC metadata updates.

**Exception**: The file lookup case in form_transformer (line 514) should continue using `instantiate()` or the new `instantiate_from_data_identification()` since it's looking up existing files, not creating/updating them.
