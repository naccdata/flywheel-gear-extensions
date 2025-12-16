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

## Form Scheduler's Event Logging Strategy

### Single Point: After Pipeline Completion

**When**: After form-scheduler pipeline completes  
**Condition**: ALWAYS (whether success or failure)  
**Metadata source**: QC log files at PROJECT level  
**Events logged**:
- `pass-qc` OR `not-pass-qc` (timestamp = completion time)

**Implementation**:
```python
# After pipeline completes
metadata = extract_metadata_from_qc_logs(module)
status = get_file_status_from_qc_logs()

if status == "PASS":
    log_event("pass-qc", timestamp=now())
else:
    log_event("not-pass-qc", timestamp=now())
```

**Note**: Submit events are handled by separate submission-logger gear, not by form-scheduler.

## No Duplicate Prevention Needed

Since form-scheduler only logs outcome events (pass-qc, not-pass-qc) and doesn't log submit events, there's no need for duplicate prevention logic. Each pipeline completion generates exactly one outcome event.

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

## Simple Integration

### EventAccumulator Class

```python
class EventAccumulator:
    """Logs outcome events after pipeline completion."""
    
    def __init__(
        self,
        event_logger: VisitEventLogger,
        module_configs: Dict[str, ModuleConfigs],
        proxy: FlywheelProxy,
    ):
        self._event_logger = event_logger
        self._module_configs = module_configs
        self._proxy = proxy
    
    def log_events(
        self,
        *,
        file: FileEntry,
        module: str,
        project: ProjectAdaptor
    ) -> None:
        """Log outcome events after pipeline completes."""
        # Extract metadata from QC log files
        metadata = self._extract_metadata_from_qc_logs(module, project)
        if not metadata:
            return
        
        # Determine outcome from QC status
        status = self._get_file_status_from_qc_logs()
        action = "pass-qc" if status == "PASS" else "not-pass-qc"
        
        # Log outcome event
        self._log_outcome_event(action, metadata, project)
```

### Integration in FormSchedulerQueue

```python
class FormSchedulerQueue:
    def __init__(self, ...):
        # ... existing code ...
        self.__event_accumulator = EventAccumulator(
            event_logger=event_logger,
            module_configs=module_configs,
            proxy=proxy
        ) if event_logger else None
    
    def _process_pipeline_queue(self, *, pipeline: Pipeline, ...):
        # ... existing code ...
        
        while len(subqueue) > 0:
            file = subqueue.pop(0)
            # ... process file ...
            
            # After: JobPoll.wait_for_pipeline(self.__proxy, job_search)
            
            # Log outcome events
            if self.__event_accumulator:
                try:
                    self.__event_accumulator.log_events(
                        file=file,
                        module=module,
                        project=self.__project
                    )
                except Exception as error:
                    log.warning(f"Failed to log events: {error}")
```

## Event Flow Examples

### Example 1: Pipeline Success

```
1. User uploads CSV
   - submit event logged by submission-logger gear
2. Form-scheduler pipeline runs
   - All gears pass
   - Events logged by form-scheduler:
     ✅ pass-qc (timestamp = completion time)
```

### Example 2: Pipeline Failure

```
1. User uploads CSV
   - submit event logged by submission-logger gear
2. Form-scheduler pipeline runs
   - Some gear fails
   - Events logged by form-scheduler:
     ✅ not-pass-qc (timestamp = completion time)
```

### Example 3: QC Alert Approval

```
1. User uploads CSV
   - submit event logged by submission-logger gear
2. Form-scheduler pipeline runs (initial)
   - QC alerts found
   - Events logged by form-scheduler:
     ✅ not-pass-qc (timestamp = completion time)
3. User approves alerts
4. Form-scheduler pipeline runs (re-evaluation)
   - Alerts cleared, now passes
   - Events logged by form-scheduler:
     ✅ pass-qc (timestamp = completion time)
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

The form-scheduler event logging strategy is simple and focused:

- **Outcome events only**: Form-scheduler logs pass-qc and not-pass-qc events
- **After pipeline completion**: Events logged when pipeline finishes processing
- **QC metadata source**: Uses QC log files to determine success/failure
- **Separation of concerns**: Submit events handled by separate submission-logger gear

This approach ensures reliable outcome event logging without interfering with pipeline execution.
