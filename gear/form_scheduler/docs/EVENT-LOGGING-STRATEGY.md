# Event Logging Strategy - Final

## Core Insight

Visit metadata availability determines when we can log events:

| Pipeline | Success | Failure | Metadata Available? | Log Events? |
|----------|---------|---------|---------------------|-------------|
| Submission | ✅ | ❌ | ❌ No | ❌ Skip |
| Submission | ❌ | ✅ | ✅ Yes (in QC log) | ✅ Log |
| Finalization | ✅ | ❌ | ✅ Yes (in JSON) | ✅ Log |
| Finalization | ❌ | ✅ | ✅ Yes (in JSON) | ✅ Log |

## Event Types

From `visit_events.py`:
- `"submit"` - Visit data submitted
- `"pass-qc"` - Visit data passed QC
- `"not-pass-qc"` - Visit data did not pass QC
- `"delete"` - Visit data deleted (not used yet)

## Two-Point Logging Strategy

### Point 1: After Submission Pipeline

**When**: After submission pipeline completes  
**Condition**: ONLY if any gear failed (QC log has errors)  
**Metadata source**: QC log file at PROJECT level  
**Events logged**:
- `submit` (timestamp = CSV upload time)
- `not-pass-qc` (timestamp = completion time)

**Implementation**:
```python
if pipeline.name == "submission":
    # Check QC log files for errors
    qc_logs_with_errors = find_qc_logs_with_errors(module)
    for qc_log in qc_logs_with_errors:
        metadata = extract_metadata(qc_log)
        log_event("submit", timestamp=csv_file.created)
        log_event("not-pass-qc", timestamp=now())
        track_logged_visit(metadata)  # Prevent duplicate in finalization
```

### Point 2: After Finalization Pipeline

**When**: After finalization pipeline completes  
**Condition**: ALWAYS (whether success or failure)  
**Metadata source**: JSON file at ACQUISITION level  
**Events logged**:
- `submit` (timestamp = JSON creation time) - ONLY if not already logged
- `pass-qc` OR `not-pass-qc` (timestamp = completion time)

**Implementation**:
```python
if pipeline.name == "finalization":
    metadata = extract_metadata(json_file)
    
    # Check if submit already logged
    if not was_submit_logged(metadata):
        log_event("submit", timestamp=json_file.created)
    
    # Always log outcome
    status = get_file_status(json_file)
    if status == "PASS":
        log_event("pass-qc", timestamp=now())
    else:
        log_event("not-pass-qc", timestamp=now())
```

## Preventing Duplicate Submit Events

Two approaches:

### Option A: In-Memory Tracking (Recommended)
```python
class VisitEventAccumulator:
    def __init__(self):
        self.__logged_submits: Set[VisitKey] = set()
    
    def log_submission_events_if_failed(self, ...):
        # ... log events ...
        self.__logged_submits.add(VisitKey(ptid, visit_date, module))
    
    def log_finalization_events(self, ...):
        key = VisitKey(ptid, visit_date, module)
        if key not in self.__logged_submits:
            log_event("submit", ...)
```

**Pros**: Fast, no S3 operations  
**Cons**: Only works within single gear execution

### Option B: S3 Check
```python
def was_submit_logged(self, metadata) -> bool:
    # List S3 objects matching pattern
    pattern = f"{env}/log-submit-*-{adcid}-{project}-{ptid}-{visitnum}.json"
    objects = s3.list_objects(pattern)
    return len(objects) > 0
```

**Pros**: Works across gear executions  
**Cons**: Requires S3 LIST operation (slower)

**Recommendation**: Use Option A (in-memory) since form-scheduler processes all files in a single execution.

## File Locations and Patterns

### QC Log Files (PROJECT level)
- **Location**: `project.files`
- **Pattern**: `{ptid}_{visitdate}_{module}_qc-status.log`
- **Example**: `110001_2024-01-15_UDS_qc-status.log`
- **Contains**: Visit metadata in `file.info` when errors occur
- **QC metadata**: `file.info.qc` with gear statuses

### JSON Files (ACQUISITION level)
- **Location**: `acquisition.files` (within session/subject hierarchy)
- **Pattern**: `{ptid}_FORMS-VISIT-{visitnum}_{module}.json`
- **Example**: `110001_FORMS-VISIT-01_UDS.json`
- **Contains**: Visit metadata in `file.info.forms.json`
- **QC metadata**: `file.info.qc` with gear statuses

## Checking QC Status

Use `FileQCModel.get_file_status()` to get overall status:

```python
from nacc_common.error_models import FileQCModel

qc_model = FileQCModel.model_validate(file.info)
status = qc_model.get_file_status()  # Returns "PASS", "FAIL", or "IN REVIEW"

if status == "PASS":
    log_event("pass-qc", ...)
else:
    log_event("not-pass-qc", ...)
```

This abstracts away the specific gear names and checks all gears in the QC metadata.

## Dynamic Dispatch with Pipeline-Specific Accumulators

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
            file: The file being processed (CSV for submission, JSON for finalization)
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
        """Log events if submission pipeline had failures."""
        # Find QC log files with errors
        qc_logs_with_errors = self._find_qc_logs_with_errors(module, project)
        
        for qc_log in qc_logs_with_errors:
            metadata = self._extract_metadata(qc_log, module)
            if not metadata:
                continue
            
            # Log submit + not-pass-qc
            self._log_submit_event(file, metadata, project)
            self._log_outcome_event("not-pass-qc", metadata, project)
            
            # Track to prevent duplicate in finalization
            key = VisitKey(metadata['ptid'], metadata['visit_date'], module)
            self._logged_submits.add(key)
    
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
        """Log events after finalization pipeline completes."""
        # Extract metadata from JSON file
        metadata = self._extract_metadata(file, module)
        if not metadata:
            return
        
        # Check if submit already logged during submission
        key = VisitKey(metadata['ptid'], metadata['visit_date'], module)
        already_logged = (
            self._submission_accumulator 
            and key in self._submission_accumulator.logged_submits
        )
        
        # Log submit if not already logged
        if not already_logged:
            self._log_submit_event(file, metadata, project)
        
        # Always log outcome
        status = self._get_file_status(file)
        action = "pass-qc" if status == "PASS" else "not-pass-qc"
        self._log_outcome_event(action, metadata, project)
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

### Integration in FormSchedulerQueue

```python
class FormSchedulerQueue:
    def __init__(self, ...):
        # ... existing code ...
        self.__event_logger = event_logger
        self.__module_configs = module_configs
        self.__submission_accumulator: Optional[SubmissionEventAccumulator] = None
    
    def _process_pipeline_queue(self, *, pipeline: Pipeline, ...):
        # ... existing code ...
        
        # Create pipeline-specific accumulator
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
            
            # Log events using dynamic dispatch
            if accumulator:
                try:
                    accumulator.log_events(
                        file=file,
                        module=module,
                        project=self.__project
                    )
                except Exception as error:
                    log.warning(f"Failed to log events: {error}")
```

## Event Flow Examples

### Example 1: Submission Success → Finalization Success

```
1. User uploads CSV
2. Submission pipeline runs
   - All gears pass
   - QC log created but no errors
   - NO events logged (no metadata available)
3. Finalization pipeline runs
   - JSON file exists with metadata
   - All gears pass
   - Events logged:
     ✅ submit (timestamp = JSON creation)
     ✅ pass-qc (timestamp = now)
```

### Example 2: Submission Failure

```
1. User uploads CSV
2. Submission pipeline runs
   - Some gear fails
   - QC log created with errors AND metadata
   - Events logged:
     ✅ submit (timestamp = CSV upload)
     ✅ not-pass-qc (timestamp = now)
3. Finalization pipeline runs (if CSV reprocessed)
   - JSON file exists with metadata
   - Check: submit already logged? YES
   - Events logged:
     ❌ submit (skip - already logged)
     ✅ pass-qc or not-pass-qc (timestamp = now)
```

### Example 3: Submission Success → Finalization Failure

```
1. User uploads CSV
2. Submission pipeline runs
   - All gears pass
   - NO events logged
3. Finalization pipeline runs
   - JSON file exists with metadata
   - Some gear fails
   - Events logged:
     ✅ submit (timestamp = JSON creation)
     ✅ not-pass-qc (timestamp = now)
```

## Key Principles

1. **Honor pipeline abstraction**: Don't assume specific gear names or order
2. **Use defined event types**: Only use `submit`, `pass-qc`, `not-pass-qc`, `delete`
3. **Log when metadata available**: Only log when we have complete visit metadata
4. **Prevent duplicates**: Track logged submits to avoid duplicate submit events
5. **Two logging points**: Submission (conditional) and finalization (always)
6. **Robust error handling**: Event logging failures don't break pipeline execution

## Testing Strategy

### Unit Tests
- QC log file discovery and error detection
- Metadata extraction from QC logs and JSON files
- Duplicate submit prevention (in-memory tracking)
- Event creation with correct timestamps

### Integration Tests
- Submission success path (no events until finalization)
- Submission failure path (events logged immediately)
- Finalization with prior submission failure (no duplicate submit)
- Multi-visit CSV with mixed results

## Summary

The event logging strategy is driven by **when visit metadata becomes available**:
- Submission failures: Metadata in QC logs → Log immediately
- Submission success: No metadata → Wait for finalization
- Finalization: Metadata in JSON → Always log

This two-point logging approach ensures we capture all visit events while avoiding duplicates and working within the constraints of the pipeline architecture.
