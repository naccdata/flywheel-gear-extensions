# Event Logging in Form Scheduler - UPDATED PLAN

## Overview

The form-scheduler gear logs visit events to track the lifecycle of form submissions through the data pipeline. This document explains how event logging works for developers unfamiliar with the gear.

**IMPORTANT**: This document reflects the updated understanding of how form-scheduler works with TWO DISTINCT PIPELINES.

## Key Insight: When Visit Metadata Becomes Available

The critical insight that drives the event logging strategy:

1. **Submission pipeline with failures**: If any gear fails, the QC log file at PROJECT level contains error details WITH visit metadata → Can log events
2. **Submission pipeline with success**: If all gears pass, there is NO sufficient visit metadata available yet → Cannot log events (must wait)
3. **Finalization pipeline**: JSON files at ACQUISITION level always contain visit metadata → Can always log events

**Therefore**: We log events at TWO points:
- After **submission pipeline** completes (ONLY if failures occurred)
- After **finalization pipeline** completes (ALWAYS, whether success or failure)

## Understanding the Two Pipelines

The form-scheduler manages two separate pipelines that work at different container levels:

### 1. Submission Pipeline (PROJECT-level files)

**What it processes**: CSV files uploaded to PROJECT level containing multiple visits

**File location**: `project.files` (PROJECT level)

**Pipeline flow**:
1. User uploads CSV file to PROJECT level (can contain multiple visits)
2. Pipeline processes the CSV through multiple gears (configured in pipeline config)
3. Pipeline ends with individual visit data in JSON files at ACQUISITION level

**Key characteristics**:
- Works with CSV files at PROJECT level
- Files are identified by tags and filename patterns (e.g., `ptid-MODULE.csv`)
- Module name extracted from filename using regex pattern
- One CSV can contain multiple visits
- Pipeline creates QC log files at PROJECT level: `{ptid}_{visitdate}_{module}_qc-status.log`
- Pipeline creates JSON files at ACQUISITION level: `{ptid}_FORMS-VISIT-{visitnum}_{module}.json`

**Challenge for event logging**: 
- Visit metadata (ptid, visit_date, visit_number) is NOT available from the CSV file itself
- Metadata only becomes available during pipeline processing (in QC log files)
- Cannot log events at queue time without this metadata

### 2. Finalization Pipeline (ACQUISITION-level files)

**What it processes**: JSON files at ACQUISITION level (created by submission pipeline)

**File location**: `acquisition.files` (ACQUISITION level, within sessions/subjects)

**Pipeline flow**:
1. JSON files already exist at ACQUISITION level (from submission pipeline)
2. Pipeline processes JSON files through multiple gears (configured in pipeline config)
3. Pipeline ensures files pass QC checks

**Key characteristics**:
- Works with JSON files at ACQUISITION level
- Files discovered using DataView API (queries across acquisitions)
- Module name comes from acquisition label
- Visit metadata already embedded in JSON files
- Each JSON represents a single visit/module combination

**Challenge for event logging**:
- These are not "new submissions" - they were already submitted in submission pipeline
- Need to distinguish between initial submission and finalization re-processing
- May need different event types or skip event logging entirely for finalization

## Revised Event Logging Strategy

Given the two-pipeline architecture, we need to revise the event logging approach:

### Option 1: Log Events Only for Submission Pipeline

**Rationale**: The submission pipeline represents the actual "submission" of new data. The finalization pipeline is just additional processing of already-submitted data.

**Implementation**:
- Only instrument the submission pipeline queue processing
- Skip event logging entirely for finalization pipeline
- Events logged: `submit`, `pass-qc`, `not-pass-qc`

**Advantages**:
- Simpler implementation
- Clear semantics: events represent actual data submission
- Avoids duplicate events for same visit

**Disadvantages**:
- Doesn't track finalization pipeline status
- May miss important QC state changes during finalization

### Option 2: Log Different Events for Each Pipeline

**Rationale**: Track both pipelines but with different event types.

**Implementation**:
- Submission pipeline: `submit`, `pass-qc-submission`, `not-pass-qc-submission`
- Finalization pipeline: `pass-qc-finalization`, `not-pass-qc-finalization`
- No `submit` event for finalization (already submitted)

**Advantages**:
- Complete tracking of both pipelines
- Can distinguish submission vs finalization QC status

**Disadvantages**:
- More complex event schema
- Consumers need to understand two sets of events
- May be overkill if finalization status not needed

### Option 3: Log Events Only When Metadata Available (Hybrid)

**Rationale**: Log events opportunistically when we have the required metadata.

**Implementation**:
- Submission pipeline: Log events after identifier-lookup creates QC log files
- Finalization pipeline: Skip event logging (or log only if needed)
- Use QC log files at PROJECT level as the source of truth for metadata

**Advantages**:
- Works within constraints of available metadata
- Focuses on submission pipeline (primary use case)
- Simpler than Option 2

**Disadvantages**:
- Cannot log `submit` event at exact queue time (must wait for QC log)
- Timestamp will be approximate (use file upload time from CSV file.created)

## Recommended Approach: Two-Point Logging Strategy

Log events at two different points based on when visit metadata becomes available.

### When to Log Events

**Submission Pipeline** (after pipeline completes):
- **If any gear failed**: QC log file contains error details with visit metadata
  - Extract visit metadata from QC log file at PROJECT level
  - Log `submit` event (timestamp = CSV upload time)
  - Log `not-pass-qc` event (timestamp = completion time)
- **If all gears passed**: No sufficient visit metadata available yet
  - Skip event logging (will log after finalization pipeline)

**Finalization Pipeline** (after pipeline completes):
- **Always log events** (visit metadata available in JSON files)
  - Extract visit metadata from JSON file at ACQUISITION level
  - Check if this is first time logging for this visit:
    - If no prior `submit` event: Log `submit` event (timestamp = JSON file creation time)
    - If prior `submit` exists: Skip submit event
  - Determine outcome based on QC status:
    - If all gears passed: Log `pass-qc` event
    - If any gear failed: Log `not-pass-qc` event

### Metadata Sources

**For submission pipeline failures**:
- QC log files at PROJECT level
- Pattern: `{ptid}_{visitdate}_{module}_qc-status.log`
- Contains visit metadata in `file.info` when errors occur
- Contains QC metadata in `file.info.qc` with error details

**For finalization pipeline (success or failure)**:
- JSON files at ACQUISITION level
- Pattern: `{ptid}_FORMS-VISIT-{visitnum}_{module}.json`
- Contains visit metadata in `file.info.forms.json`
- Contains QC metadata in `file.info.qc`
- Available when submission pipeline completed successfully

### Pipeline Success Determination

**For submission pipeline**:
- Check QC log file at PROJECT level
- If `file.info.qc` has any gear with status != "PASS": Log `not-pass-qc`
- If all gears have status "PASS": Skip logging (wait for finalization)

**For finalization pipeline**:
- Check JSON file at ACQUISITION level
- Use `FileQCModel.get_file_status()` to get overall status
- If status == "PASS": Log `pass-qc`
- If status != "PASS": Log `not-pass-qc`

### Timestamp Strategy

**submit event timestamp**: Use CSV file's `file.created` timestamp
- This represents when the user uploaded the file
- Available from the original CSV FileEntry

**outcome event timestamp**: Use current time when pipeline completes
- This represents when the pipeline finished processing
- Captured in `_process_pipeline_queue` after `JobPoll.wait_for_pipeline`

## Integration Points (Revised)

### Dynamic Dispatch with Pipeline-Specific Accumulators

Instead of conditional logic, we use **polymorphism** to handle different pipeline types.

### 1. FormSchedulerQueue.__init__

Store event logging components:

```python
def __init__(
    self,
    proxy: FlywheelProxy,
    project: ProjectAdaptor,
    pipeline_configs: PipelineConfigs,
    event_logger: Optional[VisitEventLogger] = None,
    module_configs: Optional[Dict[str, ModuleConfigs]] = None,
    email_client: Optional[EmailClient] = None,
    portal_url: Optional[URLParameter] = None,
) -> None:
    # ... existing initialization ...
    
    # Event logging components
    self.__event_logger = event_logger
    self.__module_configs = module_configs
    self.__submission_accumulator: Optional[SubmissionEventAccumulator] = None
```

### 2. _process_pipeline_queue (Both Pipelines)

Create pipeline-specific accumulator and use dynamic dispatch:

```python
def _process_pipeline_queue(
    self,
    *,
    pipeline: Pipeline,
    pipeline_queue: PipelineQueue,
    job_search: str,
    notify_user: bool,
):
    # ... existing setup code ...
    
    # Create pipeline-specific accumulator using factory
    accumulator = None
    if self.__event_logger and self.__module_configs:
        accumulator = create_event_accumulator(
            pipeline=pipeline,
            event_logger=self.__event_logger,
            module_configs=self.__module_configs,
            proxy=self.__proxy,
            submission_accumulator=self.__submission_accumulator,
        )
        
        # Store submission accumulator for finalization pipeline
        if isinstance(accumulator, SubmissionEventAccumulator):
            self.__submission_accumulator = accumulator
    
    # ... process files ...
    
    while len(subqueue) > 0:
        file = subqueue.pop(0)
        
        # ... process file ...
        
        # After: JobPoll.wait_for_pipeline(self.__proxy, job_search)
        
        # Log events using dynamic dispatch (no conditionals!)
        if accumulator:
            try:
                accumulator.log_events(
                    file=file,
                    module=module,
                    project=self.__project
                )
            except Exception as error:
                log.warning(f"Failed to log events for {file.name}: {error}")
```

## Revised Event Accumulator Architecture

### Abstract Base Class

```python
from abc import ABC, abstractmethod

class PipelineEventAccumulator(ABC):
    """Abstract base class for pipeline-specific event accumulators."""
    
    def __init__(
        self,
        event_logger: VisitEventLogger,
        module_configs: Dict[str, ModuleConfigs],
        proxy: FlywheelProxy,
    ):
        self._event_logger = event_logger
        self._module_configs = module_configs
        self._proxy = proxy
    
    @abstractmethod
    def log_events(
        self,
        *,
        file: FileEntry,
        module: str,
        project: ProjectAdaptor
    ) -> None:
        """Log events after pipeline completes.
        
        Args:
            file: The file being processed
            module: Module name
            project: Project adaptor
        """
        pass
```

### Concrete Implementations

```python
class SubmissionEventAccumulator(PipelineEventAccumulator):
    """Logs events for submission pipeline (only if failures occurred)."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logged_submits: Set[VisitKey] = set()
    
    def log_events(
        self,
        *,
        file: FileEntry,  # CSV file at PROJECT level
        module: str,
        project: ProjectAdaptor
    ) -> None:
        """Log events if submission pipeline had failures.
        
        Steps:
        1. Find QC log files at PROJECT level with errors
        2. For each failed visit:
           - Extract visit metadata from QC log
           - Log submit event (timestamp = csv_file.created)
           - Log not-pass-qc event (timestamp = current time)
           - Track logged visit to prevent duplicates
        """
        # Implementation details...
    
    @property
    def logged_submits(self) -> Set[VisitKey]:
        """Get set of logged visits (for finalization accumulator)."""
        return self._logged_submits


class FinalizationEventAccumulator(PipelineEventAccumulator):
    """Logs events for finalization pipeline (always)."""
    
    def __init__(
        self,
        *args,
        submission_accumulator: Optional[SubmissionEventAccumulator] = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._submission_accumulator = submission_accumulator
    
    def log_events(
        self,
        *,
        file: FileEntry,  # JSON file at ACQUISITION level
        module: str,
        project: ProjectAdaptor
    ) -> None:
        """Log events after finalization pipeline completes.
        
        Steps:
        1. Extract visit metadata from JSON file
        2. Check if submit already logged (via submission_accumulator)
        3. If not logged: Log submit event (timestamp = json_file.created)
        4. Check QC status using FileQCModel.get_file_status()
        5. Log outcome event (pass-qc or not-pass-qc)
        """
        # Implementation details...
```

### Factory Function

```python
def create_event_accumulator(
    pipeline: Pipeline,
    event_logger: VisitEventLogger,
    module_configs: Dict[str, ModuleConfigs],
    proxy: FlywheelProxy,
    submission_accumulator: Optional[SubmissionEventAccumulator] = None,
) -> Optional[PipelineEventAccumulator]:
    """Create appropriate accumulator for pipeline type.
    
    Args:
        pipeline: Pipeline configuration
        event_logger: Event logger
        module_configs: Module configurations
        proxy: Flywheel proxy
        submission_accumulator: Submission accumulator (for finalization)
        
    Returns:
        Pipeline-specific accumulator or None
    """
    if pipeline.name == "submission":
        return SubmissionEventAccumulator(
            event_logger=event_logger,
            module_configs=module_configs,
            proxy=proxy,
        )
    elif pipeline.name == "finalization":
        return FinalizationEventAccumulator(
            event_logger=event_logger,
            module_configs=module_configs,
            proxy=proxy,
            submission_accumulator=submission_accumulator,
        )
    return None
```

## Tracking Logged Events

To avoid duplicate `submit` events, we use **dependency injection** with pipeline-specific accumulators.

### Approach: Pass Submission Accumulator to Finalization Accumulator

The `SubmissionEventAccumulator` tracks logged visits in a set:
```python
class SubmissionEventAccumulator:
    def __init__(self, ...):
        self._logged_submits: Set[VisitKey] = set()
    
    def log_events(self, ...):
        # ... log events ...
        self._logged_submits.add(VisitKey(ptid, visit_date, module))
    
    @property
    def logged_submits(self) -> Set[VisitKey]:
        return self._logged_submits
```

The `FinalizationEventAccumulator` receives the submission accumulator:
```python
class FinalizationEventAccumulator:
    def __init__(
        self,
        *args,
        submission_accumulator: Optional[SubmissionEventAccumulator] = None,
        **kwargs
    ):
        self._submission_accumulator = submission_accumulator
    
    def log_events(self, ...):
        # Check if already logged
        key = VisitKey(ptid, visit_date, module)
        already_logged = (
            self._submission_accumulator 
            and key in self._submission_accumulator.logged_submits
        )
        
        if not already_logged:
            log_submit_event(...)
```

**Benefits**:
- Fast (in-memory, no S3 operations)
- Clean (dependency injection, no global state)
- Testable (easy to mock submission accumulator)
- Type-safe (explicit dependency)

## Key Design Decisions

### 1. Dynamic Dispatch with Polymorphism

**Decision**: Use abstract base class with concrete implementations for each pipeline type.

**Benefits**:
- No conditional logic in main code (`if pipeline.name == ...`)
- Easy to extend (add new pipeline types)
- Clean separation of concerns
- Testable in isolation

### 2. Dependency Injection for Duplicate Prevention

**Decision**: Pass submission accumulator to finalization accumulator.

**Benefits**:
- Fast (in-memory tracking)
- Clean (no global state)
- Testable (easy to mock)
- Type-safe (explicit dependency)

### 3. Two Logging Points

**Decision**: Log at submission (if failed) AND finalization (always).

**Rationale**: Visit metadata availability determines when we can log:
- Submission failures: Metadata in QC logs → Log immediately
- Submission success: No metadata → Wait for finalization
- Finalization: Metadata in JSON → Always log

### 4. Factory Pattern for Accumulator Creation

**Decision**: Use factory function to create appropriate accumulator.

**Benefits**:
- Centralized creation logic
- Easy to add new pipeline types
- Consistent initialization

### 5. Honor Pipeline Abstraction

**Decision**: Don't hardcode gear names or pipeline stages.

**Implementation**:
- Use `FileQCModel.get_file_status()` for overall status
- Don't iterate through specific gear names
- Work with any pipeline configuration

## Challenges and Limitations

### 1. Metadata Availability Timing

**Challenge**: Visit metadata is not available at consistent times:
- Submission failures: Metadata in QC log files (if errors occurred)
- Submission success: No metadata until finalization pipeline
- Finalization: Metadata always in JSON files

**Solution**: 
- Two logging points: submission (conditional) and finalization (always)
- Check QC log files for errors during submission
- Always extract from JSON files during finalization

### 2. Duplicate Submit Events

**Challenge**: Need to avoid logging `submit` event twice:
- Once during submission pipeline (if failed)
- Again during finalization pipeline (if not already logged)

**Solution**:
- Track logged visits (in-memory set or S3 check)
- Before logging submit in finalization, check if already logged
- Only log if not previously logged

### 3. Multiple Visits in One CSV

**Challenge**: A single CSV file can contain multiple visits:
- Each visit may succeed or fail independently
- Need to log separate events for each visit

**Solution**: 
- Submission: Iterate through all QC log files with errors for the module
- Finalization: Process one JSON file at a time (already separated)
- Log events independently for each visit

### 4. Pipeline Configuration Generality

**Challenge**: Pipeline configuration is parameterized:
- Don't know specific gear names
- Don't know pipeline stages
- Must work with any configuration

**Solution**:
- Use `pipeline.name` to identify submission vs finalization
- Use `FileQCModel.get_file_status()` for overall status (abstracts gear details)
- Don't hardcode gear names or assumptions

### 5. Early Pipeline Failures

**Challenge**: If pipeline fails before QC log files are created:
- No QC log file exists
- No visit metadata available
- Cannot log events during submission

**Solution**:
- Accept this limitation for submission pipeline
- Events will be logged during finalization (if pipeline eventually succeeds)
- If pipeline never succeeds, no events logged (acceptable - no visit data created)

## Testing Considerations

### Submission Pipeline Tests

1. **Submission with failures**: QC log has errors
   - Verify submit + not-pass-qc events logged
   - Verify events have correct timestamps
   
2. **Submission with success**: No errors in QC log
   - Verify NO events logged during submission
   - Events will be logged during finalization

3. **Multi-visit CSV with mixed results**: Some visits fail, some succeed
   - Verify events logged only for failed visits
   - Successful visits logged during finalization

4. **Early failure**: No QC log files created
   - Verify no events logged
   - Acceptable limitation

### Finalization Pipeline Tests

1. **Finalization success**: All gears pass
   - Verify submit + pass-qc events logged
   - Verify submit not duplicated if already logged

2. **Finalization failure**: Some gears fail
   - Verify submit + not-pass-qc events logged
   - Verify submit not duplicated if already logged

3. **Already logged during submission**: Visit failed in submission
   - Verify submit event NOT logged again
   - Verify outcome event IS logged (may be different from submission)

### Integration Tests

1. **End-to-end success path**: CSV → submission success → finalization success
   - Verify events logged only during finalization
   - Verify submit + pass-qc events

2. **End-to-end failure path**: CSV → submission failure
   - Verify events logged during submission
   - Verify submit + not-pass-qc events

3. **Partial failure path**: CSV → submission failure → finalization success
   - Verify submit + not-pass-qc during submission
   - Verify NO submit during finalization (already logged)
   - Verify pass-qc during finalization

## Next Steps

1. Update `VisitEventAccumulator` to implement new single-method API
2. Remove two-phase accumulation logic (record_file_queued, pending data)
3. Implement QC log file discovery and matching logic
4. Implement multi-visit handling (iterate through QC logs)
5. Update integration points in `FormSchedulerQueue`
6. Add pipeline name check to skip finalization pipeline
7. Update tests to reflect new approach
8. Update implementation guide document

## Summary

The revised approach uses **dynamic dispatch with pipeline-specific accumulators**:

### Architecture
- **Abstract base class**: `PipelineEventAccumulator` defines interface
- **Concrete implementations**: 
  - `SubmissionEventAccumulator` - logs only if failures occurred
  - `FinalizationEventAccumulator` - always logs events
- **Factory function**: Creates appropriate accumulator based on pipeline type
- **Dependency injection**: Finalization accumulator receives submission accumulator

### Key Features
- ✅ **Clean code**: No conditional logic (`if pipeline.name == ...`)
- ✅ **Extensible**: Easy to add new pipeline types
- ✅ **Testable**: Each accumulator isolated and mockable
- ✅ **Type-safe**: Abstract interface enforced
- ✅ **Maintainable**: Clear separation of concerns

### Event Logging Strategy
- **Submission pipeline**: Log only if failures occurred (QC log has errors)
- **Finalization pipeline**: Always log events (JSON has metadata)
- **Duplicate prevention**: Finalization checks submission accumulator's logged visits
- **Two metadata sources**: QC log files (submission) and JSON files (finalization)
- **Pipeline abstraction**: Use `FileQCModel.get_file_status()`, no hardcoded gear names

### Integration
```python
# Create accumulator using factory (no conditionals!)
accumulator = create_event_accumulator(pipeline, ...)

# Log events using dynamic dispatch
if accumulator:
    accumulator.log_events(file=file, module=module, project=project)
```

This approach works within the constraints of the two-pipeline architecture and provides reliable event logging driven by when visit metadata becomes available.
