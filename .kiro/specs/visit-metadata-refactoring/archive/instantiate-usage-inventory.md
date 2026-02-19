# Template.instantiate() Usage Inventory

This document tracks all uses of `instantiate()` methods across the codebase to ensure proper migration to the new `DataIdentification`-based API.

## Template Types

### 1. ErrorLogTemplate (error_logging/error_logger.py)
Used for generating QC status log filenames.

**Current API:**
```python
instantiate(record: dict, module: str) -> Optional[str]
```

**New API (to be added):**
```python
instantiate_from_data_identification(data_id: DataIdentification) -> Optional[str]
```

### 2. LabelTemplate (configs/ingest_configs.py)
Used for generating session/acquisition labels and filenames during data upload.

**Current API:**
```python
instantiate(record: dict, environment: Optional[dict] = None) -> str
```

**Status:** Different use case - works with raw CSV records for Flywheel hierarchy labels. Uses Python's `string.Template` for variable substitution, making it more general-purpose than ErrorLogTemplate's fixed format.

**Note:** Consider whether LabelTemplate's more flexible approach could replace or unify with ErrorLogTemplate's fixed format logic. LabelTemplate supports:
- Arbitrary template strings with `$variable` substitution
- Optional transforms (upper/lower case)
- Environment variable support
- Delimiter customization

This might be more maintainable than ErrorLogTemplate's hardcoded field order and formatting.

---

## ErrorLogTemplate Usage Locations

### Production Code

#### 1. common/src/python/error_logging/qc_status_log_creator.py
**Lines:** 177-179, 241
**Pattern:** DataIdentification → dict conversion → instantiate()
```python
record = self._prepare_template_record(visit_keys)  # visit_keys is DataIdentification
error_log_name = self.__template.instantiate(record=record, module=visit_keys.module)
```
**Migration:** Replace with `instantiate_from_data_identification(visit_keys)`

#### 2. common/src/python/event_capture/event_processor.py
**Lines:** 354-356
**Pattern:** dict (forms_json) → instantiate()
```python
qc_log_name = self._error_log_template.instantiate(
    record=forms_json, module=module
)
```
**Context:** `forms_json` is from file.info["forms"]["json"]
**Migration:** May need to create DataIdentification from forms_json first

#### 3. gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py
**Lines:** 304-306
**Pattern:** Manual dict construction → instantiate()
```python
error_log_name = ErrorLogTemplate().instantiate(
    record={
        f"{FieldNames.PTID}": ptid,
        # ... other fields
    },
    module=module
)
```
**Migration:** Create DataIdentification from available fields, then use new method

#### 4. gear/form_transformer/src/python/form_csv_app/main.py
**Lines:** 408-410, 514-516
**Pattern:** Raw CSV record → instantiate()
```python
error_log_name = self.__errorlog_template.instantiate(
    module=self.module, record=input_record
)
```
**Context:** `input_record` is raw CSV row dict
**Migration:** Create DataIdentification from input_record first

#### 5. gear/form_qc_checker/src/python/form_qc_app/processor.py
**Lines:** 169-171
**Pattern:** Raw CSV record → instantiate()
```python
error_log_name = self._errorlog_template.instantiate(
    record=input_record, module=self._module
)
```
**Migration:** Create DataIdentification from input_record first

#### 6. gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py
**Lines:** 57
**Pattern:** dict (forms_json) → instantiate()
```python
return self.__error_log_template.instantiate(record=forms_json, module=module)
```
**Context:** `forms_json` is from file metadata
**Migration:** Create DataIdentification from forms_json first

#### 7. gear/identifier_provisioning/src/python/identifier_provisioning_app/main.py
**Lines:** 92-94
**Pattern:** Raw CSV record → instantiate()
```python
error_log_name = errorlog_template.instantiate(
    module=DefaultValues.ENROLLMENT_MODULE, record=input_record
)
```
**Migration:** Create DataIdentification from input_record first

#### 8. gear/participant_transfer/src/python/participant_transfer_app/transfer.py
**Lines:** 442-444
**Pattern:** Manual dict construction → instantiate()
```python
error_log_name = errorlog_template.instantiate(
    module=DefaultValues.ENROLLMENT_MODULE, record=transfer_record
)
```
**Migration:** Create DataIdentification from transfer_record first

### Test Code

#### 9. common/test/python/outputs/test_project_report_visitor.py
**Lines:** 78-80
**Pattern:** Manual dict construction → instantiate()
```python
log_filename = ErrorLogTemplate().instantiate(
    {"ptid": visit_details.ptid, "visitdate": visit_details.date},
    module=visit_details.module,
)
```
**Migration:** Test code - can use either old or new API

#### 10. gear/form_transformer/test/python/test_uds_transform.py
**Lines:** 265-267, 300-302
**Pattern:** Raw record → instantiate()
```python
file_name = ErrorLogTemplate().instantiate(
    module=record["module"], record=record
)
```
**Migration:** Test code - can use either old or new API

#### 11. gear/form_scheduler/test/python/test_property_event_structure_compatibility.py
**Lines:** 159-161, 271-273, 348-350, 427-429
**Pattern:** forms_json dict → instantiate()
```python
qc_filename = error_log_template.instantiate(
    record=forms_json, module=forms_json["module"]
)
```
**Migration:** Test code - can use either old or new API

#### 12. gear/form_scheduler/test/python/test_property_qc_pass_event_creation.py
**Lines:** 68-70, 176-178, 247-249
**Pattern:** forms_json dict → instantiate()
```python
qc_filename = error_log_template.instantiate(
    record=forms_json, module=forms_json["module"]
)
```
**Migration:** Test code - can use either old or new API

---

## LabelTemplate Usage - Out of Scope

`LabelTemplate` (from `configs/ingest_configs.py`) is used for Flywheel hierarchy labels (session/acquisition/filename) during data upload, not for error log filenames. It uses a different pattern (string.Template with variable substitution) and works with raw CSV records.

**Usage locations:** `common/src/python/uploads/uploader.py` and related tests.

**No migration needed** - serves a different purpose than ErrorLogTemplate.

---

## Migration Strategy

### Phase 1: Add New Method
- [x] Add `instantiate_from_data_identification()` to ErrorLogTemplate
- [ ] Add tests for new method
- [ ] Ensure backward compatibility with existing `instantiate()` method

### Phase 2: Update Production Code (Priority Order)

**High Priority - Already using DataIdentification:**
1. `common/src/python/error_logging/qc_status_log_creator.py` - Already has DataIdentification, just needs method swap

**Medium Priority - Need to create DataIdentification:**
2. `common/src/python/event_capture/event_processor.py` - forms_json from file metadata
3. `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py` - forms_json from file metadata

**Lower Priority - Raw CSV processing:**
4. `gear/form_transformer/src/python/form_csv_app/main.py` - input_record from CSV
5. `gear/form_qc_checker/src/python/form_qc_app/processor.py` - input_record from CSV
6. `gear/identifier_provisioning/src/python/identifier_provisioning_app/main.py` - input_record from CSV
7. `gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py` - manual dict construction
8. `gear/participant_transfer/src/python/participant_transfer_app/transfer.py` - manual dict construction

### Phase 3: Update Test Code
- Update tests to use new API where appropriate
- Keep some tests using old API to ensure backward compatibility

### Phase 4: Deprecation (Future)
- Mark old `instantiate()` method as deprecated
- Add deprecation warnings
- Plan removal timeline

---

## Notes

### Field Name Mapping
The old API expects `visitdate` but DataIdentification uses `date`. The `_prepare_template_record()` method in qc_status_log_creator.py handles this mapping:
```python
record["visitdate"] = record.pop("date")
```

The new `instantiate_from_data_identification()` method should handle this mapping internally.

### Module Parameter
The old API takes `module` as a separate parameter. With DataIdentification, module is part of the `data.module` field (for FormIdentification).

### LabelTemplate vs ErrorLogTemplate
LabelTemplate is used for different purposes (Flywheel hierarchy labels) and may not need DataIdentification support. It works with raw CSV records that may not have visit metadata structure.
