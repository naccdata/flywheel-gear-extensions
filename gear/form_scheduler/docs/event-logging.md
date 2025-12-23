# Event Logging in Form Scheduler

## Overview

The form-scheduler gear logs visit outcome events (`pass-qc`, `not-pass-qc`) after pipeline completion. Submit events are handled separately by the identifier-lookup gear.

## What Events Are Logged

The form-scheduler logs two types of outcome events:

- **pass-qc**: Visit successfully completed all QC checks
- **not-pass-qc**: Visit failed QC validation

**Note**: Submit events are logged by the identifier-lookup gear when CSV files are processed.

## Implementation

### EventAccumulator Class

Located in: `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py`

The `EventAccumulator` class handles outcome event logging:

```python
class EventAccumulator:
    """Simplified event accumulator for QC-pass events only."""
    
    def __init__(self, event_logger: VisitEventLogger) -> None:
        self.__event_logger = event_logger
    
    def log_events(self, json_file: FileEntry, project: ProjectAdaptor) -> None:
        """Log outcome events based on QC status."""
```

### Integration Point

The event accumulator is called in `FormSchedulerQueue._log_pipeline_events()` after pipeline completion:

```python
# After pipeline completes
if self.__event_logger:
    try:
        from form_scheduler_app.event_accumulator import EventAccumulator
        event_accumulator = EventAccumulator(event_logger=self.__event_logger)
        event_accumulator.log_events(json_file=json_file, project=self.__project)
    except Exception as error:
        log.warning(f"Failed to log events: {error}")
```

## Event Determination Logic

Events are determined by checking QC status in JSON files at the ACQUISITION level:

1. **Find JSON file**: Locate the visit's JSON file using `ErrorLogTemplate`
2. **Extract metadata**: Get visit metadata from QC status or JSON file metadata
3. **Check QC status**: Determine if visit passed or failed QC
4. **Log event**: Create and log appropriate outcome event

### QC Status Checking

The system checks QC status from the JSON file's custom info:

```python
def is_qc_pass(json_file: FileEntry) -> bool:
    """Check if visit passed QC based on file metadata."""
    if not json_file.info:
        return False
    
    qc_status = json_file.info.get("qc_status")
    return qc_status == QC_STATUS_PASS
```

## Event Data Structure

Events use the `VisitEvent` model from `common/src/python/event_logging/visit_events.py`:

```python
class VisitEvent(BaseModel):
    action: VisitEventType          # "pass-qc" or "not-pass-qc"
    study: str                      # "adrc"
    pipeline_adcid: int             # Center ADCID
    project_label: str              # Project name
    center_label: str               # Center name
    gear_name: str                  # "form-scheduler"
    ptid: str                       # Participant ID
    visit_date: str                 # Visit date (YYYY-MM-DD)
    visit_number: Optional[str]     # Visit number
    datatype: DatatypeNameType      # "form"
    module: Optional[ModuleName]    # Module name (UDS, FTLD, etc.)
    packet: Optional[str]           # Packet type
    timestamp: datetime             # When event occurred
```

## Configuration

Event logging is configured through gear parameters:

- **`environment`**: Environment for event logging ("prod" or "dev")
- **`event_bucket`**: S3 bucket name for storing events

## Error Handling

Event logging includes robust error handling:

- Event logging failures do not affect pipeline execution
- Errors are logged as warnings but don't fail the gear
- Missing metadata results in skipped event logging
- Invalid QC status is handled gracefully

## Event Storage

Events are stored in S3 with the following structure:

```
s3://{bucket-name}/
├── prod/
│   ├── log-pass-qc-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
│   └── log-not-pass-qc-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
└── dev/
    └── ...
```

Filename format: `log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json`

## Key Design Principles

1. **Separation of concerns**: Submit events (identifier-lookup) vs outcome events (form-scheduler)
2. **Non-invasive**: Event logging doesn't change pipeline execution
3. **Simplified approach**: Only logs events for JSON files that exist (successful pipeline completion)
4. **Robust error handling**: Failures don't break pipeline execution
5. **QC-based determination**: Uses existing QC infrastructure to determine success/failure

## Testing

Event logging is tested through:

- Unit tests for `EventAccumulator` class
- Integration tests with `FormSchedulerQueue`
- Property-based tests for event structure compatibility
- End-to-end tests for various QC scenarios

See test files in `gear/form_scheduler/test/python/test_*event*.py` for comprehensive test coverage.