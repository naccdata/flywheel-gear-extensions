# Event Logging Implementation Guide

## Overview

This document provides implementation details for the event logging feature in form-scheduler. It's intended for developers working on the codebase.

## Architecture

### Two-Phase Accumulation Strategy

Event logging uses a two-phase approach for newly submitted visits:

**Phase 1: Capture Upload Information**
- When a CSV file is queued for processing
- Records upload timestamp and project metadata
- Stores data in memory keyed by visit_number
- Only applies to newly uploaded files

**Phase 2: Finalize and Log Events**
- After pipeline completes
- Retrieves visit metadata from JSON files
- Creates and logs events (submit + outcome)
- Cleans up pending data

**Re-evaluation Scenarios**: Visits that are re-evaluated (e.g., after dependency resolution) skip Phase 1 since they were already submitted. Only outcome events are logged.

## Key Classes

### VisitEventAccumulator

Located in: `gear/form_scheduler/src/python/form_scheduler_app/form_scheduler_queue.py`

Manages the event logging lifecycle:

```python
class VisitEventAccumulator:
    """Accumulates visit event data throughout pipeline processing."""
    
    def __init__(
        self,
        event_logger: VisitEventLogger,
        module_configs: ModuleConfigs,
        proxy: FlywheelProxy
    )
    
    def record_file_queued(
        self,
        *,
        file: FileEntry,
        module: str,
        project: Project
    ) -> None:
        """Record when a file is queued (Phase 1)."""
    
    def finalize_and_log_events(
        self,
        *,
        file: FileEntry,
        module: str,
        pipeline_succeeded: bool
    ) -> None:
        """Complete metadata and log events (Phase 2)."""
```

### PendingVisitData

Pydantic model holding partial visit data:

```python
class PendingVisitData(BaseModel):
    visit_number: str              # Tracking key
    session_id: str                # Session container ID
    acquisition_id: str            # Acquisition container ID
    module: str                    # Module name
    project_label: str             # Project label
    center_label: str              # Center label
    pipeline_adcid: int            # ADCID for routing
    upload_timestamp: datetime     # For "submit" event
    completion_timestamp: Optional[datetime] = None
    csv_filename: str = ""         # For debugging
```

## Integration Points

### 1. FormSchedulerQueue.__init__

Create the accumulator:

```python
self.__event_accumulator = VisitEventAccumulator(
    event_logger=event_logger,
    module_configs=module_configs,
    proxy=proxy
)
```

### 2. _add_submission_pipeline_files

After adding file to queue (~line 230):

```python
if pipeline_queue.add_file_to_subqueue(module=module, file=file):
    # Record upload information
    self.__event_accumulator.record_file_queued(
        file=file,
        module=module,
        project=project
    )
    num_files += 1
```

### 3. _process_pipeline_queue

After pipeline completes (~line 481):

```python
JobPoll.wait_for_pipeline(self.__proxy, job_search)

# Determine success
pipeline_succeeded = self.__check_pipeline_success(file, module)

# Finalize and log events
try:
    self.__event_accumulator.finalize_and_log_events(
        file=file,
        module=module,
        pipeline_succeeded=pipeline_succeeded
    )
except Exception as error:
    log.warning(f"Failed to log events for {file.name}: {error}")
```

## Success/Failure Detection

### __check_pipeline_success Method

**"pass-qc" event is ONLY logged when BOTH conditions are met:**
1. JSON file exists at ACQUISITION level (proves form-transformer succeeded)
2. ALL pipeline gears have status="PASS" in QC metadata

```python
def __check_pipeline_success(self, file: FileEntry, module: str) -> bool:
    """Check if pipeline completed successfully.
    
    Returns True ONLY if:
    1. JSON file exists at ACQUISITION level
    2. ALL gears have status="PASS"
    """
    acquisition = self.__proxy.get_container_by_id(file.parent_ref.id)
    
    # Find JSON file
    json_file = self.__find_json_file(acquisition, module)
    if not json_file:
        return False  # No JSON = early failure
    
    # Parse QC metadata
    from nacc_common.error_models import FileQCModel
    qc_model = FileQCModel.model_validate(json_file.info)
    
    # Check ALL gears
    pipeline_gears = ['form-screening', 'form-transformer', 'form-qc-checker']
    for gear_name in pipeline_gears:
        status = qc_model.get_status(gear_name)
        if status != "PASS":
            return False
    
    return True
```

## Visit Number Extraction

Visit numbers are extracted from session labels using module config templates:

```python
def __extract_visit_number_from_session(
    self,
    session_label: str,
    module: str
) -> Optional[str]:
    """Extract visit number from session label.
    
    Example:
        Template: "FORMS-VISIT-${visitnum}"
        Label: "FORMS-VISIT-01"
        Returns: "01"
    """
    module_config = self.__module_configs.get(module.upper())
    hierarchy = module_config.hierarchy_labels
    session_config = hierarchy['session']
    template = session_config.get('template', '')
    
    # Convert template to regex
    pattern = template.replace('${visitnum}', r'(\d+)')
    pattern = pattern.replace('-', r'\-')
    
    # Apply transform
    transform = session_config.get('transform', '')
    if transform == 'upper':
        session_label = session_label.upper()
    
    # Extract
    match = re.match(pattern, session_label)
    return match.group(1) if match else None
```

## Visit Metadata Extraction

Uses existing infrastructure from `nacc_common`:

```python
def __extract_visit_metadata(
    self,
    json_file: FileEntry,
    module: str
) -> Optional[Dict[str, Any]]:
    """Extract visit metadata from JSON file."""
    
    form_metadata = json_file.info.get('forms', {}).get('json', {})
    module_config = self.__module_configs.get(module.upper())
    
    # Use VisitKeys.create_from() - standard way to extract visit data
    from nacc_common.error_models import VisitKeys
    date_field = module_config.date_field
    visit_keys = VisitKeys.create_from(form_metadata, date_field)
    
    # Parse date
    from dates.dates import datetime_from_form_date
    visit_datetime = datetime_from_form_date(visit_keys.date)
    visit_date = visit_datetime.date()
    
    # Get packet
    from nacc_common.field_names import FieldNames
    packet = form_metadata.get(FieldNames.PACKET)
    
    return {
        'ptid': visit_keys.ptid,
        'visit_date': visit_date,
        'visit_number': visit_keys.visitnum,
        'packet': str(packet) if packet else None
    }
```

## Event Creation

Both events are created in `finalize_and_log_events`:

```python
# Submit event (always logged for new submissions)
submit_event = VisitEvent(
    action="submit",
    pipeline_adcid=pending.pipeline_adcid,
    project_label=pending.project_label,
    center_label=pending.center_label,
    gear_name="form-scheduler",
    ptid=visit_metadata['ptid'],
    visit_date=visit_metadata['visit_date'],
    visit_number=visit_metadata['visit_number'],
    datatype="form",
    module=pending.module,
    packet=visit_metadata.get('packet'),
    timestamp=pending.upload_timestamp  # Upload time
)
self.__event_logger.log_event(submit_event)

# Outcome event
outcome_action = "pass-qc" if pipeline_succeeded else "not-pass-qc"
outcome_event = VisitEvent(
    action=outcome_action,
    # ... same fields ...
    timestamp=pending.completion_timestamp  # Completion time
)
self.__event_logger.log_event(outcome_event)
```

## Dependencies

### Required Imports

```python
from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent
from configs.ingest_configs import ModuleConfigs
from nacc_common.error_models import VisitKeys, FileQCModel
from nacc_common.field_names import FieldNames
from dates.dates import datetime_from_form_date
```

### Required Inputs

The gear needs `form_configs_file` input in manifest.json:

```json
{
  "inputs": {
    "form_configs_file": {
      "base": "file",
      "description": "Form module configurations file",
      "optional": false
    }
  }
}
```

## Known Limitations

1. **Visit number requirement**: Only works for modules with visit numbers in session labels
2. **JSON file requirement**: Cannot log events for early pipeline failures (no JSON file)
3. **Re-evaluation scenarios**: Currently returns early if no pending data exists
   - Need to handle pass-qc events without corresponding submit events
   - Example: Follow-up visits blocked on UDS packet, re-evaluated after UDS clears

## Error Handling

All event logging errors are caught and logged as warnings:

```python
try:
    self.__event_accumulator.finalize_and_log_events(...)
except Exception as error:
    log.warning(f"Failed to log events for {file.name}: {error}")
```

This ensures event logging failures don't break pipeline execution.

## Testing Considerations

1. **Unit tests**: Mock FileEntry, Project, FlywheelProxy
2. **Integration tests**: Mock pipeline execution
3. **Test scenarios**:
   - Successful pipeline (both events logged)
   - Failed pipeline (submit + not-pass-qc)
   - Missing visit number (skip logging)
   - Missing JSON file (skip logging)
   - Re-evaluation (only outcome event)

## Future Enhancements

1. Support modules without visit numbers (alternative tracking keys)
2. Handle early pipeline failures (use QC log files at PROJECT level)
3. Full re-evaluation support (pass-qc without submit in same job)
4. Parameterize status handling for different pipeline types
