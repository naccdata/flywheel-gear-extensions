# Event Logging Implementation - Changes Summary

## What Changed

After reviewing the refactored `form_scheduler_queue.py`, we discovered that our original understanding was incorrect. This document summarizes the key changes to the event logging plan.

## Original Understanding (INCORRECT)

We thought:
- Form scheduler processes files in a single pipeline
- Files are queued and processed one at a time
- Visit metadata is available when files are queued
- We can log "submit" events immediately when files are queued
- We can log outcome events after pipeline completes

## Correct Understanding

The form scheduler actually:
- Manages **TWO DISTINCT PIPELINES**: submission and finalization
- Processes files at **DIFFERENT CONTAINER LEVELS**: PROJECT vs ACQUISITION
- Visit metadata is **NOT AVAILABLE** when CSV files are queued
- Metadata only becomes available **AFTER identifier-lookup** creates QC log files

## The Two Pipelines

### 1. Submission Pipeline (PROJECT-level)

**What**: Processes CSV files uploaded to PROJECT level

**Flow**:
1. User uploads CSV (can contain multiple visits)
2. Pipeline processes CSV through multiple gears (configured in pipeline config)
3. Pipeline ends with individual visit data in JSON files at ACQUISITION level

**Key Points**:
- Works with CSV files at PROJECT level
- Module name extracted from filename pattern
- One CSV can contain multiple visits
- Pipeline creates QC logs at PROJECT: `{ptid}_{visitdate}_{module}_qc-status.log`
- Pipeline creates JSON at ACQUISITION: `{ptid}_FORMS-VISIT-{visitnum}_{module}.json`

### 2. Finalization Pipeline (ACQUISITION-level)

**What**: Processes JSON files at ACQUISITION level

**Flow**:
1. JSON files already exist (from submission pipeline)
2. Pipeline processes JSON files through multiple gears (configured in pipeline config)
3. Pipeline ensures files pass QC checks

**Key Points**:
- Works with JSON files at ACQUISITION level
- Uses DataView API to find files across acquisitions
- These are NOT new submissions (already submitted)

## Major Changes to Event Logging Plan

### 1. No Two-Phase Accumulation

**Old approach**:
- Phase 1: Record data when file queued
- Phase 2: Complete data and log events after pipeline

**New approach**:
- Single phase: Log everything after pipeline completes
- No pending data storage needed

**Reason**: Visit metadata not available at queue time

### 2. No record_file_queued Method

**Old approach**:
- Call `record_file_queued()` when file added to queue
- Store partial data for later completion

**New approach**:
- Don't log anything at queue time
- Wait until pipeline completes and metadata is available

**Reason**: Cannot extract visit metadata from CSV file itself

### 3. Use QC Log Files for Metadata

**Old approach**:
- Extract metadata from JSON files at ACQUISITION level

**New approach**:
- Extract metadata from QC log files at PROJECT level
- QC logs created earlier (by identifier-lookup)
- More reliable than JSON files

**Reason**: QC logs always exist at PROJECT level, easier to find

### 4. Handle Multiple Visits Per CSV

**Old approach**:
- Assumed one file = one visit

**New approach**:
- Find ALL QC log files for the module
- Log separate events for each visit
- Iterate through QC logs

**Reason**: One CSV can contain multiple visits

### 5. Submission Pipeline Only

**Old approach**:
- Log events for all files processed

**New approach**:
- Only log events for submission pipeline
- Skip finalization pipeline entirely

**Reason**: Finalization is not a new submission, would create duplicate events

### 6. Check Pipeline Name

**Old approach**:
- Instrument all pipeline processing

**New approach**:
- Check `if pipeline.name == "submission"`
- Only log events for submission pipeline

**Reason**: Need to distinguish between submission and finalization

### 7. Simplified API

**Old API**:
```python
accumulator.record_file_queued(file, module, project)
# ... pipeline runs ...
accumulator.log_outcome_event(file, module, success)
```

**New API**:
```python
# ... pipeline runs ...
accumulator.log_events_for_file(csv_file, module, pipeline)
```

**Reason**: Single logging point, simpler implementation

## Implementation Changes

### What to Remove

1. `record_file_queued()` method
2. `log_outcome_event()` method  
3. `__pending` dictionary
4. `PendingVisitData` class
5. Two-phase accumulation logic
6. `submit_logged` flag

### What to Keep

1. `__extract_visit_metadata()` method
2. `__find_qc_log_file()` method (modify to find multiple)
3. `VisitEvent` model
4. `VisitEventLogger` class

### What to Add

1. `__find_qc_log_files_for_module()` - find all QC logs for module
2. `__check_pipeline_success_for_visit()` - check success for specific visit
3. `__log_events_for_visit()` - log submit + outcome for one visit
4. `__log_events_for_file()` - log events for all visits in CSV
5. Pipeline name check: `if pipeline.name == "submission"`

## Integration Point Changes

### Old Integration

```python
# In queue_files_for_pipeline (when file queued)
accumulator.record_file_queued(file, module, project)

# In _process_pipeline_queue (after pipeline completes)
success = check_pipeline_success(file, module)
accumulator.log_outcome_event(file, module, success)
```

### New Integration

```python
# Nothing at queue time

# In _process_pipeline_queue (after pipeline completes)
if pipeline.name == "submission" and accumulator:
    try:
        accumulator.log_events_for_file(csv_file, module, pipeline)
    except Exception as error:
        log.warning(f"Failed to log events: {error}")
```

## Key Insights

1. **Metadata availability**: Visit metadata only exists AFTER identifier-lookup runs, not at queue time

2. **File locations matter**: CSV at PROJECT level, JSON at ACQUISITION level - different containers

3. **Multiple visits**: One CSV can contain many visits, need to handle each separately

4. **Two pipelines**: Submission (new data) vs Finalization (reprocessing) - only log for submission

5. **QC logs are key**: QC log files at PROJECT level are the reliable source of visit metadata

6. **Simpler is better**: Single logging point is simpler than two-phase accumulation

## Testing Impact

### Old Test Cases

- Test record_file_queued with/without JSON
- Test log_outcome_event with/without pending data
- Test two-phase accumulation
- Test pending data cleanup

### New Test Cases

- Test finding multiple QC log files
- Test extracting metadata from QC logs
- Test checking success for specific visit
- Test logging events for multi-visit CSV
- Test skipping finalization pipeline
- Test timestamp filtering for QC logs

## Documentation Updates

Created three new documents:

1. **event-logging-UPDATED.md**: High-level overview with correct understanding
2. **event-logging-implementation-UPDATED.md**: Detailed implementation guide
3. **CHANGES-SUMMARY.md**: This document

Original documents remain for reference but should not be used for implementation.

## Next Steps

1. Review updated documentation with team
2. Confirm approach is correct
3. Implement changes to `VisitEventAccumulator`
4. Update integration in `FormSchedulerQueue`
5. Update tests
6. Test with real data

## Questions to Resolve

1. **QC log matching**: How to reliably match QC logs to the CSV that triggered them?
   - Current approach: Use timestamp filtering (QC logs created after CSV modified time)
   - Alternative: Store CSV file ID in QC log metadata

2. **Early failures**: What to do if pipeline fails before QC log files are created?
   - Current approach: Log warning, skip event logging
   - Alternative: Create minimal events with available data

3. **Finalization events**: Do we need to log events for finalization pipeline?
   - Current approach: Skip finalization entirely
   - Alternative: Log different event types for finalization

4. **Reprocessing**: How to handle same CSV processed multiple times?
   - Current approach: Log events each time (may create duplicates)
   - Alternative: Track logged events, skip duplicates

## Summary

The refactored code revealed that form-scheduler is more complex than we initially understood. The two-pipeline architecture and the delayed availability of visit metadata require a simpler, single-point logging approach rather than the two-phase accumulation we originally planned.

The updated plan:
- ✅ Simpler implementation (single logging point)
- ✅ More accurate (uses QC logs as source of truth)
- ✅ Handles multiple visits (iterates through QC logs)
- ✅ Submission pipeline only (skips finalization)
- ✅ Robust error handling (failures don't break pipeline)

This approach works within the constraints of the actual architecture and provides reliable event logging for form submissions.
