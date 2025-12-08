# Event Logging Implementation Guide - UPDATED

## Overview

This document provides implementation details for the REVISED event logging feature in form-scheduler, based on the correct understanding of the two-pipeline architecture.

## Key Changes from Original Plan

The original plan assumed we could log events when files were queued. However, we now understand:

1. **Two distinct pipelines**: Submission (PROJECT-level CSV files) and Finalization (ACQUISITION-level JSON files)
2. **Metadata not available at queue time**: Visit metadata only exists AFTER identifier-lookup creates QC log files
3. **Multiple visits per file**: One CSV can contain multiple visits, each needs separate events
4. **Different file locations**: CSV at PROJECT level, JSON at ACQUISITION level

## Revised Architecture

### Dynamic Dispatch with Pipeline-Specific Accumulators

Event logging uses **polymorphism** to handle different pipeline types:

1. **Abstract base class**: `PipelineEventAccumulator` defines interface
2. **Concrete implementations**: 
   - `SubmissionEventAccumulator` - logs only if failures occurred
   - `FinalizationEventAccumulator` - always logs events
3. **Factory function**: Creates appropriate accumulator based on pipeline type
4. **Dynamic dispatch**: Call `accumulator.log_events()` regardless of pipeline type

**Benefits**:
- Clean separation of concerns
- No conditional logic in main code
- Easy to add new pipeline types
- Testable in isolation

### Two Logging Points

**Submission Pipeline**:
- Logs events ONLY if any gear failed (QC log has errors)
- Tracks logged visits to prevent duplicates

**Finalization Pipeline**:
- Always logs events (JSON has metadata)
- Checks if submit already logged (via submission accumulator)
- Logs submit only if not already logged

## Implementation Strategy

### Step 1: Define Abstract Base Class

```python
from abc import ABC, abstractmethod
from typing import Dict, Optional, Set

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
    
    def _extract_metadata(
        self,
        file: FileEntry,
        module: str
    ) -> Optional[Dict[str, Any]]:
        """Extract visit metadata from file.
        
        Shared implementation for both pipeline types.
        """
        # Implementation here (same as before)
        pass
    
    def _log_submit_event(
        self,
        file: FileEntry,
        metadata: Dict[str, Any],
        project: ProjectAdaptor
    ) -> None:
        """Log submit event.
        
        Shared implementation for both pipeline types.
        """
        # Implementation here
        pass
    
    def _log_outcome_event(
        self,
        action: str,
        metadata: Dict[str, Any],
        project: ProjectAdaptor
    ) -> None:
        """Log outcome event (pass-qc or not-pass-qc).
        
        Shared implementation for both pipeline types.
        """
        # Implementation here
        pass
```

### Step 2: Implement Submission Accumulator

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
        
        Only logs if QC log files contain errors with visit metadata.
        """
        # Find QC log files with errors for this module
        qc_logs_with_errors = self._find_qc_logs_with_errors(
            module=module,
            project=project,
            after_timestamp=file.modified
        )
        
        if not qc_logs_with_errors:
            log.info(
                f"No QC log errors found for {file.name}. "
                f"Events will be logged during finalization."
            )
            return
        
        # Log events for each failed visit
        for qc_log in qc_logs_with_errors:
            try:
                metadata = self._extract_metadata(qc_log, module)
                if not metadata:
                    continue
                
                # Log submit event (timestamp = CSV upload time)
                self._log_submit_event(file, metadata, project)
                
                # Log not-pass-qc event (timestamp = current time)
                self._log_outcome_event("not-pass-qc", metadata, project)
                
                # Track to prevent duplicate in finalization
                key = VisitKey(
                    metadata['ptid'],
                    metadata['visit_date'].isoformat(),
                    module.upper()
                )
                self._logged_submits.add(key)
                
                log.info(
                    f"Logged submission failure events for "
                    f"{metadata['ptid']} visit {metadata['visit_number']}"
                )
                
            except Exception as error:
                log.error(
                    f"Error logging events for {qc_log.name}: {error}",
                    exc_info=True
                )
    
    @property
    def logged_submits(self) -> Set[VisitKey]:
        """Get set of logged visits (for finalization accumulator)."""
        return self._logged_submits
    
    def _find_qc_logs_with_errors(
        self,
        module: str,
        project: ProjectAdaptor,
        after_timestamp: datetime
    ) -> List[FileEntry]:
        """Find QC log files with errors for this module."""
        qc_log_pattern = f"_{module.upper()}_qc-status.log"
        
        # Reload project to get latest files
        project = project.reload()
        
        # Find matching QC log files created after timestamp
        qc_logs = [
            f for f in project.files
            if f.name.endswith(qc_log_pattern)
            and f.modified >= after_timestamp
        ]
        
        # Filter to only those with errors
        qc_logs_with_errors = []
        for qc_log in qc_logs:
            if self._has_qc_errors(qc_log):
                qc_logs_with_errors.append(qc_log)
        
        return qc_logs_with_errors
    
    def _has_qc_errors(self, qc_log: FileEntry) -> bool:
        """Check if QC log file has any errors."""
        try:
            from nacc_common.error_models import FileQCModel
            qc_model = FileQCModel.model_validate(qc_log.info)
            status = qc_model.get_file_status()
            return status != "PASS"
        except Exception:
            return False
```

### Step 3: Implement Finalization Accumulator

```python
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
        
        Always logs events (visit metadata available in JSON file).
        Checks if submit already logged during submission.
        """
        try:
            # Extract metadata from JSON file
            metadata = self._extract_metadata(file, module)
            if not metadata:
                log.warning(f"Could not extract metadata from {file.name}")
                return
            
            # Check if submit already logged during submission
            key = VisitKey(
                metadata['ptid'],
                metadata['visit_date'].isoformat(),
                module.upper()
            )
            already_logged = (
                self._submission_accumulator 
                and key in self._submission_accumulator.logged_submits
            )
            
            # Log submit if not already logged
            if not already_logged:
                self._log_submit_event(file, metadata, project)
                log.info(
                    f"Logged submit event for {metadata['ptid']} "
                    f"visit {metadata['visit_number']}"
                )
            else:
                log.info(
                    f"Skipping submit event for {metadata['ptid']} "
                    f"visit {metadata['visit_number']} (already logged)"
                )
            
            # Always log outcome
            status = self._get_file_status(file)
            action = "pass-qc" if status == "PASS" else "not-pass-qc"
            self._log_outcome_event(action, metadata, project)
            
            log.info(
                f"Logged {action} event for {metadata['ptid']} "
                f"visit {metadata['visit_number']}"
            )
            
        except Exception as error:
            log.error(
                f"Error logging finalization events for {file.name}: {error}",
                exc_info=True
            )
    
    def _get_file_status(self, file: FileEntry) -> str:
        """Get overall QC status from JSON file."""
        try:
            from nacc_common.error_models import FileQCModel
            qc_model = FileQCModel.model_validate(file.info)
            return qc_model.get_file_status()
        except Exception as error:
            log.warning(f"Failed to get file status: {error}")
            return "FAIL"  # Default to FAIL if can't determine
```

### Step 4: Create Factory Function

```python
def create_event_accumulator(
    pipeline: Pipeline,
    event_logger: VisitEventLogger,
    module_configs: Dict[str, ModuleConfigs],
    proxy: FlywheelProxy,
    submission_accumulator: Optional[SubmissionEventAccumulator] = None,
) -> Optional[PipelineEventAccumulator]:
    """Create appropriate accumulator for pipeline type.
    
    Uses factory pattern to instantiate correct accumulator based on
    pipeline name.
    
    Args:
        pipeline: Pipeline configuration
        event_logger: Event logger
        module_configs: Module configurations
        proxy: Flywheel proxy
        submission_accumulator: Submission accumulator (for finalization)
        
    Returns:
        Pipeline-specific accumulator or None if unsupported pipeline
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
    else:
        log.warning(f"Unknown pipeline type: {pipeline.name}")
        return None
```

### Step 5: Integrate in FormSchedulerQueue

Update the constructor and pipeline processing:

```python
class FormSchedulerQueue:
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
        """Initializer.
        
        Args:
            proxy: the proxy for the Flywheel instance
            project: Flywheel project container
            pipeline_configs: form pipeline configurations
            event_logger: Event logger (optional)
            module_configs: Module configurations (optional)
            email_client: EmailClient to send emails from
            portal_url: The portal URL
        """
        self.__proxy = proxy
        self.__project = project
        self.__pipeline_configs = pipeline_configs
        self.__email_client = email_client
        self.__portal_url = portal_url
        self.__pipeline_queues: Dict[str, PipelineQueue] = {}
        
        # Event logging components
        self.__event_logger = event_logger
        self.__module_configs = module_configs
        self.__submission_accumulator: Optional[SubmissionEventAccumulator] = None
    
    def _process_pipeline_queue(
        self,
        *,
        pipeline: Pipeline,
        pipeline_queue: PipelineQueue,
        job_search: str,
        notify_user: bool,
    ):
        """Process files in a pipeline queue using round-robin scheduling."""
        
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
        
        # ... existing pipeline processing code ...
        
        while not pipeline_queue.empty():
            module, subqueue = pipeline_queue.next_queue()
            if not subqueue:
                continue
            
            # ... set gear inputs ...
            
            while len(subqueue) > 0:
                file = subqueue.pop(0)
                
                # ... remove tags, trigger gear ...
                
                # d. Wait for the triggered pipeline to complete
                JobPoll.wait_for_pipeline(self.__proxy, job_search)
                
                # Log events using dynamic dispatch
                if accumulator:
                    try:
                        accumulator.log_events(
                            file=file,
                            module=module,
                            project=self.__project
                        )
                    except Exception as error:
                        log.warning(
                            f"Failed to log events for {file.name}: {error}",
                            exc_info=True
                        )
                
                # e. Send notification email if enabled
                # ... existing notification code ...
```

### Step 6: Log Events

Create and log both events:

```python
def __log_events_for_visit(
    self,
    *,
    csv_file: FileEntry,
    qc_log_file: FileEntry,
    module: str,
    pipeline_succeeded: bool
) -> None:
    """Log submit and outcome events for a single visit.
    
    Args:
        csv_file: Original CSV file (for upload timestamp)
        qc_log_file: QC log file (for visit metadata)
        module: Module name
        pipeline_succeeded: Whether pipeline succeeded
    """
    # Extract visit metadata
    visit_metadata = self.__extract_visit_metadata(qc_log_file, module)
    if not visit_metadata:
        log.warning(f"Could not extract metadata from {qc_log_file.name}")
        return
    
    # Get project metadata
    project = self.__project
    pipeline_adcid = project.info.get("pipeline_adcid")
    if not pipeline_adcid:
        log.warning(f"No pipeline_adcid in project {project.label}")
        return
    
    # Create submit event (timestamp = CSV upload time)
    submit_event = VisitEvent(
        action="submit",
        pipeline_adcid=pipeline_adcid,
        project_label=project.label,
        center_label=project.group,
        gear_name="form-scheduler",
        ptid=visit_metadata["ptid"],
        visit_date=visit_metadata["visit_date"],
        visit_number=visit_metadata["visit_number"],
        datatype="form",
        module=module.upper(),
        packet=visit_metadata.get("packet"),
        timestamp=csv_file.created  # Upload time
    )
    self.__event_logger.log_event(submit_event)
    
    # Create outcome event (timestamp = current time)
    outcome_action = "pass-qc" if pipeline_succeeded else "not-pass-qc"
    outcome_event = VisitEvent(
        action=outcome_action,
        pipeline_adcid=pipeline_adcid,
        project_label=project.label,
        center_label=project.group,
        gear_name="form-scheduler",
        ptid=visit_metadata["ptid"],
        visit_date=visit_metadata["visit_date"],
        visit_number=visit_metadata["visit_number"],
        datatype="form",
        module=module.upper(),
        packet=visit_metadata.get("packet"),
        timestamp=datetime.now()  # Completion time
    )
    self.__event_logger.log_event(outcome_event)
    
    log.info(
        f"Logged events for {visit_metadata['ptid']} "
        f"visit {visit_metadata['visit_number']}: "
        f"submit + {outcome_action}"
    )
```

### Step 7: Handle Multiple Visits

Iterate through all QC log files for the module:

```python
def __log_events_for_file(
    self,
    *,
    csv_file: FileEntry,
    module: str,
    pipeline: Pipeline
) -> None:
    """Log events for all visits in the CSV file.
    
    A single CSV can contain multiple visits. We need to:
    1. Find all QC log files for this module
    2. Filter to only those created during this pipeline run
    3. Log events for each visit
    
    Args:
        csv_file: Original CSV file at PROJECT level
        module: Module name
        pipeline: Pipeline configuration
    """
    # Find QC log files created after CSV was queued
    # Use CSV modified time as cutoff (files created after this are from current run)
    qc_logs = self.__find_qc_log_files_for_module(
        module=module,
        after_timestamp=csv_file.modified
    )
    
    if not qc_logs:
        log.warning(
            f"No QC log files found for {csv_file.name} module {module}. "
            f"Pipeline may have failed before identifier-lookup."
        )
        return
    
    log.info(f"Found {len(qc_logs)} QC log files for {csv_file.name}")
    
    # Log events for each visit
    for qc_log in qc_logs:
        try:
            # Extract metadata to get ptid and visit_number
            visit_metadata = self.__extract_visit_metadata(qc_log, module)
            if not visit_metadata:
                continue
            
            # Check if pipeline succeeded for this visit
            pipeline_succeeded = self.__check_pipeline_success_for_visit(
                ptid=visit_metadata["ptid"],
                visit_number=visit_metadata["visit_number"],
                module=module
            )
            
            # Log events
            self.__log_events_for_visit(
                csv_file=csv_file,
                qc_log_file=qc_log,
                module=module,
                pipeline_succeeded=pipeline_succeeded
            )
            
        except Exception as error:
            log.error(
                f"Error logging events for {qc_log.name}: {error}",
                exc_info=True
            )
```

## Simplified VisitEventAccumulator

The accumulator no longer needs to accumulate anything. It's just a helper class:

```python
class VisitEventAccumulator:
    """Helper class for logging visit events.
    
    No longer accumulates data over time. Just provides utility methods
    for extracting metadata and logging events.
    """
    
    def __init__(
        self,
        event_logger: VisitEventLogger,
        module_configs: Dict[str, ModuleConfigs],
        proxy: FlywheelProxy,
    ):
        self.__event_logger = event_logger
        self.__module_configs = module_configs
        self.__proxy = proxy
    
    # Remove: record_file_queued (no longer needed)
    # Remove: log_outcome_event (replaced with simpler methods)
    # Remove: __pending dict (no longer needed)
    
    # Keep: __extract_visit_metadata (still needed)
    # Keep: __find_qc_log_file (still needed, but modify to find multiple)
    
    # Add: Methods for finding subjects/sessions/acquisitions
    # Add: Method for checking pipeline success
    # Add: Method for logging events for a visit
```

## Integration in FormSchedulerQueue

### Constructor

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
    # ... existing code ...
    
    # Create event accumulator if event logging enabled
    self.__event_accumulator = None
    if event_logger and module_configs:
        self.__event_accumulator = VisitEventAccumulator(
            event_logger=event_logger,
            module_configs=module_configs,
            proxy=proxy
        )
```

### In _process_pipeline_queue

```python
# After: JobPoll.wait_for_pipeline(self.__proxy, job_search)

# Log events for submission pipeline only
if pipeline.name == "submission" and self.__event_accumulator:
    try:
        self.__log_events_for_file(
            csv_file=file,
            module=module,
            pipeline=pipeline
        )
    except Exception as error:
        log.warning(
            f"Failed to log events for {file.name}: {error}",
            exc_info=True
        )
```

## Dependencies

### Required Imports

```python
from datetime import datetime
from typing import Dict, List, Optional

from event_logging.event_logging import VisitEventLogger
from event_logging.visit_events import VisitEvent
from configs.ingest_configs import ModuleConfigs
from nacc_common.error_models import VisitKeys, FileQCModel
from nacc_common.field_names import FieldNames
from dates.dates import datetime_from_form_date
```

### Required Configuration

The gear needs:
1. `form_configs_file` input (for module configurations)
2. `event_bucket` config parameter (S3 bucket name)
3. AWS credentials (for S3 access)

## Error Handling

All event logging is wrapped in try/except:

```python
try:
    self.__log_events_for_file(...)
except Exception as error:
    log.warning(f"Failed to log events: {error}", exc_info=True)
```

This ensures event logging failures don't break pipeline execution.

## Testing Strategy

### Unit Tests

1. **QC log file discovery**:
   - Single visit
   - Multiple visits
   - No QC logs (early failure)
   - QC logs from previous runs (timestamp filtering)

2. **Metadata extraction**:
   - Valid QC log
   - Missing fields
   - Invalid date format

3. **Pipeline success checking**:
   - All gears PASS
   - Any gear FAIL
   - No JSON file
   - Missing QC metadata

4. **Event logging**:
   - Single visit success
   - Single visit failure
   - Multiple visits mixed success/failure

### Integration Tests

1. **End-to-end submission pipeline**:
   - Upload CSV
   - Process through pipeline
   - Verify events logged to S3

2. **Finalization pipeline**:
   - Process JSON files
   - Verify NO events logged

3. **Multi-visit CSV**:
   - Upload CSV with 3 visits
   - Verify 6 events logged (3 submit + 3 outcome)

## Migration from Old Implementation

### Remove

1. `record_file_queued` method
2. `log_outcome_event` method
3. `__pending` dictionary
4. `PendingVisitData` class
5. Two-phase accumulation logic

### Keep

1. `__extract_visit_metadata` method
2. `__find_qc_log_file` method (modify to find multiple)
3. `VisitEvent` model
4. `VisitEventLogger` class

### Add

1. `__find_qc_log_files_for_module` method
2. `__check_pipeline_success_for_visit` method
3. `__log_events_for_visit` method
4. `__log_events_for_file` method
5. Helper methods for finding subjects/sessions/acquisitions

## Known Limitations

1. **Early pipeline failures**: If pipeline fails before QC log files are created, no visit metadata is available, so no events can be logged.

2. **Timestamp precision**: Submit event uses CSV `file.created` timestamp, which may not be exact upload time if file was modified.

3. **QC log matching**: We use timestamp filtering to match QC logs to CSV files. If multiple CSVs are processed simultaneously, this could be imprecise.

4. **Finalization pipeline**: No events logged for finalization pipeline. If this is needed in the future, will require separate implementation.

5. **Pipeline gear assumptions**: We don't know which specific gears are in the pipeline (configured via pipeline config), so we check overall file status rather than individual gear names.

## Future Enhancements

1. **Finalization events**: Add support for logging finalization pipeline events with different event types.

2. **Better QC log matching**: Store CSV file ID in QC log metadata to enable precise matching.

3. **Batch event logging**: Log all events for a CSV in a single S3 write operation.

4. **Event deduplication**: Track logged events to avoid duplicates if CSV is reprocessed.

## Benefits of Dynamic Dispatch Approach

### 1. Clean Separation of Concerns
- Each accumulator handles its own pipeline type
- No conditional logic in main code (`if pipeline.name == ...`)
- Single responsibility principle

### 2. Extensibility
- Easy to add new pipeline types (just create new accumulator class)
- No changes to FormSchedulerQueue needed
- Factory pattern handles instantiation

### 3. Testability
- Each accumulator can be tested in isolation
- Mock dependencies easily
- Clear interfaces

### 4. Type Safety
- Abstract base class enforces interface
- IDE autocomplete works correctly
- Compile-time checking (with type hints)

### 5. Maintainability
- Pipeline-specific logic stays in pipeline-specific classes
- Changes to one pipeline don't affect others
- Clear code organization

## Summary

The revised implementation uses **dynamic dispatch with pipeline-specific accumulators**:
- **Abstract base class**: `PipelineEventAccumulator` defines interface
- **Concrete implementations**: `SubmissionEventAccumulator` and `FinalizationEventAccumulator`
- **Factory function**: Creates appropriate accumulator based on pipeline type
- **Single call site**: `accumulator.log_events()` works for all pipeline types
- **Shared functionality**: Common methods in base class
- **Pipeline-specific logic**: Overridden in concrete classes

This approach provides:
- ✅ Clean code (no conditionals)
- ✅ Easy to extend (add new pipeline types)
- ✅ Easy to test (isolated classes)
- ✅ Type safe (abstract interface)
- ✅ Maintainable (clear organization)

The implementation works within the constraints of the two-pipeline architecture and provides reliable event logging for form submissions.
