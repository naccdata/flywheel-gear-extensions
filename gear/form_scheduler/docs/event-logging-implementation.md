# Event Logging Implementation Guide

## Overview

This document provides implementation details for the revised event logging feature. It's intended for developers working on the codebase.

## Architecture

### Form Scheduler's Event Logging

The form-scheduler gear handles outcome event logging:

**visitor_event_accumulator**
- Runs in form-scheduler after pipeline completes
- Scrapes qc-status log files for QC metadata
- Logs "pass-qc" or "not-pass-qc" events based on QC status
- Uses visitor pattern to traverse QC metadata structure

**Benefits**:
- Outcome events captured after pipeline processing
- QC status log files serve as single source of truth
- Non-invasive: doesn't interfere with pipeline execution
- Uses existing QC infrastructure for reliable status detection

## Key Classes

### EventAccumulator

Located in: `gear/form_scheduler/src/python/form_scheduler_app/visitor_event_accumulator.py`

Manages outcome event logging after pipeline completes:

```python
class EventAccumulator:
    """Scrapes qc-status log files to log outcome events."""
    
    def __init__(
        self,
        pipeline: Pipeline,
        event_logger: VisitEventLogger
    )
    
    def log_events(
        self,
        file: FileEntry,
        project: ProjectAdaptor
    ) -> None:
        """Log outcome events by scraping qc-status logs."""
```

### VisitKey

Composite key for uniquely identifying a visit:

```python
class VisitKey(BaseModel):
    """Composite key for uniquely identifying a visit."""
    
    model_config = ConfigDict(frozen=True)
    
    ptid: str
    visit_date: str
    module: str
```

### Visitor Pattern Classes

Uses visitor pattern to traverse QC metadata:

- **FirstErrorVisitor**: Finds the first error in QC metadata (for timestamp/gear info)
- **EventTableVisitor**: Processes error reports and logs events
- **ProjectReportVisitor**: Orchestrates traversal of project files

## Integration Points

### 1. Form Scheduler Integration

The event accumulator is integrated into form-scheduler's pipeline processing.

### 2. FormSchedulerQueue.__init__

Create the event accumulator:

```python
self.__event_accumulator = EventAccumulator(
    pipeline=pipeline,
    event_logger=event_logger
)
```

### 3. _process_pipeline_queue

After pipeline completes:

```python
JobPoll.wait_for_pipeline(self.__proxy, job_search)

# Log outcome events by scraping qc-status logs
if self.__event_accumulator:
    try:
        self.__event_accumulator.log_events(
            file=file,
            project=self.__project
        )
    except Exception as error:
        log.warning(f"Failed to log events for {file.name}: {error}")
```

## Success/Failure Detection

### QC Status from qc-status Log Files

The visitor_event_accumulator scrapes QC status from qc-status log files at PROJECT level:

```python
def log_events(self, file: FileEntry, project: ProjectAdaptor) -> None:
    """Log events by scraping qc-status logs."""
    
    # Create visitor to traverse qc-status logs
    error_visitor = ProjectReportVisitor(
        adcid=project.get_pipeline_adcid(),
        modules=set(self.__pipeline.modules),
        file_visitor=FirstErrorVisitor(error_transformer),
        table_visitor=EventTableVisitor(self.__event_logger),
        file_filter=create_modified_filter(file.created)
    )
    
    # Visit project and scrape QC metadata
    error_visitor.visit_project(project)
```

**How it works:**
1. Filters qc-status log files modified after file upload
2. Uses visitor pattern to traverse QC metadata structure
3. FirstErrorVisitor finds first error (if any) for timestamp/gear info
4. EventTableVisitor processes error reports and logs events
5. QC status determined from FileQCModel.get_file_status()

**Benefits:**
- No hardcoded gear names or pipeline stages
- Works with any pipeline configuration
- Leverages existing QC infrastructure

## Metadata Extraction

### From qc-status Log Files

Visit metadata is extracted from qc-status log files at PROJECT level:

**File naming pattern**: `{ptid}_{visitdate}_{module}_qc-status.log`

Example: `110001_2024-01-15_UDS_qc-status.log`

**QC metadata structure** in `file.info.qc`:
```yaml
file.info:
  forms:
    json:
      ptid: "110001"
      visitnum: "01"
      visitdate: "2024-01-15"
      packet: "I"
      module: "UDS"
  qc:
    form-screening:
      validation:
        state: "PASS"
    identifier-lookup:
      validation:
        state: "PASS"
    form-transformer:
      validation:
        state: "PASS"
    form-qc-checker:
      validation:
        state: "PASS"
```

The visitor pattern traverses this structure to extract:
- Visit metadata (ptid, visit_date, visit_number, packet)
- QC status from all gears
- Error details (if any)

### Visitor Pattern for Metadata Extraction

The visitor pattern provides flexible traversal of QC metadata:

```python
class FirstErrorVisitor(ErrorReportVisitor):
    """Finds the FIRST FileError in QC metadata."""
    
    def visit_file_model(self, file_model: FileQCModel) -> None:
        """Visit file model and stop after finding first error."""
        if self.table:
            return
        super().visit_file_model(file_model)
    
    def visit_validation_model(self, validation_model: ValidationModel) -> None:
        """Visit validation model and check for errors."""
        if self.table:
            return
        
        state = validation_model.state
        if state is not None and state.lower() == "pass":
            return
        
        # Found a non-pass state, get first error
        if validation_model.data:
            validation_model.data[0].apply(self)


class EventTableVisitor(ReportTableVisitor):
    """Processes error reports and logs events."""
    
    def __init__(self, event_logger: VisitEventLogger) -> None:
        self.__event_logger = event_logger
        self.__logged_submits: set[VisitKey] = set()
    
    def visit_row(self, row: QCReportBaseModel) -> None:
        """Process error report row and log events."""
        if not isinstance(row, ErrorReportModel):
            return
        
        # Extract metadata from row
        # Log submit event (if not already logged)
        # Log outcome event based on QC status
```

## Event Creation

### Outcome Events Only

Form-scheduler only creates outcome events (submit events handled separately):

Created after pipeline completes by scraping qc-status logs:

```python
# Determine outcome from QC status
qc_status = FileQCModel.get_file_status()
outcome_action = "pass-qc" if qc_status == "PASS" else "not-pass-qc"

outcome_event = VisitEvent(
    action=outcome_action,
    pipeline_adcid=project.get_pipeline_adcid(),
    project_label=project.label,
    center_label=project.group,
    gear_name="form-scheduler",
    ptid=visit_metadata['ptid'],
    visit_date=visit_metadata['visit_date'],
    visit_number=visit_metadata['visit_number'],
    datatype="form",
    module=module,
    packet=visit_metadata.get('packet'),
    timestamp=datetime.now()  # Completion time
)
event_logger.log_event(outcome_event)
```

## Dependencies

### Required Imports (visitor_event_accumulator)

```python
from configs.ingest_configs import Pipeline
from event_logging.event_logging import VisitEventLogger
from flywheel.models.file_entry import FileEntry
from flywheel_adaptor.flywheel_proxy import ProjectAdaptor
from nacc_common.error_models import FileQCModel, ValidationModel
from nacc_common.qc_report import (
    ErrorReportVisitor,
    ErrorTransformer,
    ProjectReportVisitor,
    QCReportBaseModel,
    ReportTableVisitor,
)
from nacc_common.visit_submission_error import ErrorReportModel, error_transformer
```

### Required Configuration

**form-scheduler gear:**
- `form_configs_file` input (for module configurations)
- `event_bucket` config parameter (S3 bucket name)
- AWS credentials (for S3 access)

## Known Limitations

1. **qc-status log requirement**: Requires qc-status log files to exist at PROJECT level
2. **Visitor pattern complexity**: Requires understanding of visitor pattern and QC metadata structure
3. **Duplicate submit prevention**: Currently tracks in-memory, may log duplicate submits across gear executions
4. **File filtering**: Uses file modification timestamp to filter relevant qc-status logs (may be imprecise)

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

### visitor_event_accumulator Tests
1. **Unit tests**: Mock FileEntry, ProjectAdaptor, visitor classes
2. **Integration tests**: Mock qc-status log files with QC metadata
3. **Test scenarios**:
   - Successful pipeline (pass-qc event logged)
   - Failed pipeline (not-pass-qc event logged)
   - Multiple qc-status logs (multiple events logged)
   - No qc-status logs (no events logged)
   - File filtering by timestamp (only relevant logs processed)

## Future Enhancements

1. **Persistent duplicate tracking**: Store logged submits in S3 to prevent duplicates across executions
2. **Better file filtering**: Use file metadata or tags to match qc-status logs to processed files
3. **Event deduplication**: Check S3 before logging to avoid duplicate events
4. **Batch event logging**: Log multiple events in single S3 operation for efficiency
5. **Support for finalization pipeline**: Extend to log events for JSON files in finalization pipeline
