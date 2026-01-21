# Event Logging in Form Scheduler

## Overview

The form-scheduler gear logs "pass-qc" events when visits successfully complete QC validation. Submit events are handled separately by the identifier-lookup gear.

## What Events Are Logged

The form-scheduler logs one type of outcome event:

- **pass-qc**: Visit successfully completed all QC checks

**Note**: Submit events are logged by the identifier-lookup gear when CSV files are processed.

## Implementation

### EventAccumulator Class

Located in: `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py`

The `EventAccumulator` class handles pass-qc event logging:

```python
class EventAccumulator:
    """Simplified event accumulator for QC-pass events only."""
    
    def __init__(self, event_capture: VisitEventCapture) -> None:
        self.__event_capture = event_capture
        self.__error_log_template = ErrorLogTemplate()
    
    def capture_events(self, json_file: FileEntry, project: ProjectAdaptor) -> None:
        """Log QC-pass events for a JSON file if it passes QC validation."""
```

### Integration Point

The event accumulator is called in `FormSchedulerQueue._log_pipeline_events()` during finalization queue processing:

```python
def _log_pipeline_events(self, json_file: FileEntry) -> None:
    """Log pass-qc events for finalized JSON files."""
    if not self.__event_capture:
        return
    
    try:
        from form_scheduler_app.event_accumulator import EventAccumulator
        event_accumulator = EventAccumulator(event_capture=self.__event_capture)
        event_accumulator.capture_events(json_file=json_file, project=self.__project)
    except Exception as error:
        log.warning(f"Failed to log events: {error}")
```

## Event Determination Logic

Events are determined by checking QC status in qc-status log files at the PROJECT level:

1. **Find QC status log**: Use `ErrorLogTemplate` to generate expected filename from JSON file metadata
2. **Extract metadata**: Get visit metadata from QC status custom info or JSON file metadata
3. **Check QC status**: Use `FileQCModel.get_file_status()` to determine if visit passed QC
4. **Log event**: Create and log pass-qc event if status is PASS

### QC Status Checking

The system checks QC status from the qc-status log file:

```python
def _check_qc_status(qc_log_file: FileEntry) -> bool:
    """Check if QC status is PASS."""
    try:
        qc_model = FileQCModel.model_validate(qc_log_file.info)
    except ValidationError:
        return False
    
    file_status = qc_model.get_file_status()
    return file_status == QC_STATUS_PASS
```

### Metadata Extraction

Visit metadata is extracted with priority:

1. First try QC status log custom info (contains VisitMetadata)
2. Fall back to JSON file forms.json metadata

```python
def _extract_visit_metadata(
    json_file: FileEntry, 
    qc_log_file: Optional[FileEntry]
) -> Optional[VisitMetadata]:
    """Extract visit metadata with priority: QC status, then JSON file."""
    # Try QC status custom info first
    if qc_log_file and qc_log_file.info:
        visit_metadata = VisitMetadataExtractor.from_qc_status_custom_info(
            qc_log_file.info
        )
        if visit_metadata and VisitMetadataExtractor.is_valid_for_event(visit_metadata):
            return visit_metadata
    
    # Fall back to JSON file metadata
    visit_metadata = VisitMetadataExtractor.from_json_file_metadata(json_file)
    if visit_metadata and VisitMetadataExtractor.is_valid_for_event(visit_metadata):
        return visit_metadata
    
    return None
```

## Event Data Structure

Events use the `VisitEvent` model from `common/src/python/event_capture/visit_events.py`:

```python
class VisitEvent(BaseModel):
    action: VisitEventType          # "pass-qc"
    study: str                      # Extracted from project label
    pipeline_adcid: int             # Center ADCID
    project_label: str              # Project name
    center_label: str               # Center name
    gear_name: str                  # "form-scheduler"
    ptid: str                       # Participant ID
    visit_date: str                 # Visit date (YYYY-MM-DD)
    visit_number: Optional[str]     # Visit number (optional)
    datatype: DatatypeNameType      # "form"
    module: Optional[ModuleName]    # Module name (UDS, FTLD, etc.)
    packet: Optional[str]           # Packet type (optional)
    timestamp: datetime             # QC log modification time
```

## Configuration

Event logging is configured through gear parameters:

- **`event_environment`**: Environment for event logging ("prod" or "dev")
- **`event_bucket`**: S3 bucket name for storing events

Both parameters are optional. If not provided, event logging is disabled.

## Error Handling

Event logging includes robust error handling:

- Event logging failures do not affect pipeline execution
- Errors are logged as warnings but don't fail the gear
- Missing QC status log results in skipped event logging (debug message)
- QC status not PASS results in skipped event logging (debug message)
- Missing or invalid metadata results in skipped event logging (warning message)
- All exceptions are caught and logged with full traceback

## Event Storage

Events are stored in S3 with the following structure:

```
s3://{bucket-name}/
├── prod/
│   └── log-pass-qc-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json
└── dev/
    └── ...
```

Filename format: `log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visitnum}.json`

Where:

- **action**: "pass-qc"
- **timestamp**: QC log modification time in format YYYYMMDD-HHMMSS
- **adcid**: Pipeline ADCID
- **project**: Project label (sanitized)
- **ptid**: Participant ID
- **visitnum**: Visit number (or "None" if not present)

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
