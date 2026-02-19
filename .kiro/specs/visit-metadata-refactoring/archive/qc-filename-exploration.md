# QC Status Log Filename Exploration

## Goal

Make QC status log filenames better represent the DataIdentification structure while maintaining backward compatibility.

## Current State

**Format:** `{ptid}_{date}_{module}_qc-status.log`

**Example:** `12345_2024-01-15_a1_qc-status.log`

**Issues:**
- Uses `module` field for both form names and image modalities (conceptual mixing)
- Doesn't include `visitnum` or `packet` which are part of DataIdentification
- Loses information that could help distinguish different data

## Key Insights

1. **No collision risk** - Each project is scoped to one center (group), so ptid is unique within a project
2. **Backward compatibility required** - Old filenames must still be found during lookup
3. **Conceptual clarity** - Filenames should reflect DataIdentification structure:
   - Forms have: ptid, date, form name (module), packet
   - Images have: ptid, date, modality (not really a "module")

## Solution: Conditional Filename Components

**New Format:**
```
{ptid}[_{visitnum}]_{date}_{module}[_{packet}]_qc-status.log
```

Where `[_{field}]` means "include if non-None"

### Examples

**Form with visitnum and packet:**
```
ptid=12345, visitnum=001, date=2024-01-15, module=a1, packet=i
→ 12345_001_2024-01-15_a1_i_qc-status.log
```

**Form with packet but no visitnum (non-visit form):**
```
ptid=12345, visitnum=None, date=2024-01-15, module=np, packet=i
→ 12345_2024-01-15_np_i_qc-status.log
```

**Form with visitnum but no packet:**
```
ptid=12345, visitnum=001, date=2024-01-15, module=a1, packet=None
→ 12345_001_2024-01-15_a1_qc-status.log
```

**Legacy format (backward compatible):**
```
ptid=12345, visitnum=None, date=2024-01-15, module=a1, packet=None
→ 12345_2024-01-15_a1_qc-status.log
```

**Image data:**
```
ptid=12345, visitnum=None, date=2024-01-20, module=mr, packet=None
→ 12345_2024-01-20_mr_qc-status.log
```

## Implementation

### New Methods Added to ErrorLogTemplate

#### 1. `instantiate_from_data_identification(data_id: DataIdentification) -> Optional[str]`

Generates filename directly from DataIdentification, preserving the structure:
- Includes visitnum if present
- Includes packet if present (forms only)
- Maintains backward compatibility when fields are None

#### 2. `get_possible_filenames(data_id: DataIdentification) -> list[str]`

Returns list of possible filenames for lookup, in priority order:
1. New format with all available fields
2. Format without packet (if packet was present)
3. Format without visitnum (if visitnum was present)
4. Legacy format (no visitnum, no packet)

This supports backward compatibility when looking up existing files.

### Backward Compatibility Strategy

**For file creation:**
- Use `instantiate_from_data_identification()` to generate new format

**For file lookup:**
- Use `get_possible_filenames()` to try multiple formats
- Try new format first, fall back to legacy formats
- Existing code using `instantiate(record, module)` continues to work

### Legacy Method Preserved

The existing `instantiate(record: Dict[str, Any], module: str)` method remains unchanged for backward compatibility with existing code.

## Benefits

1. **Richer information** - Filenames now include visitnum and packet when available
2. **Conceptual clarity** - Filename structure matches DataIdentification model
3. **Backward compatible** - Old filenames still work, lookup tries multiple formats
4. **No collisions** - Still unique within project scope
5. **Extensible** - Easy to add new fields for future datatypes

## Testing

Comprehensive pytest tests added in:
`common/test/python/error_logging/test_error_log_template_data_identification.py`

Tests cover:
- All filename format variations
- Backward compatibility
- Missing field handling
- Lookup fallback order
- Field normalization (lowercase, leading zeros)

## Next Steps

To fully adopt this in the codebase:

1. **Update QCStatusLogManager** to use `instantiate_from_data_identification()`
2. **Update file lookup code** to use `get_possible_filenames()` for backward compatibility
3. **Update EventAccumulator** in form_scheduler to use new methods
4. **Update EventProcessor** in event_capture to use new methods
5. **Run integration tests** to verify backward compatibility
6. **Document migration** for any external code that generates QC log filenames

## Files Modified

- `common/src/python/error_logging/error_logger.py` - Added new methods to ErrorLogTemplate
- `common/test/python/error_logging/test_error_log_template_data_identification.py` - New test file

## Status

✅ Exploration complete
✅ Implementation complete
✅ Tests passing
⏳ Integration with rest of codebase (next step)
