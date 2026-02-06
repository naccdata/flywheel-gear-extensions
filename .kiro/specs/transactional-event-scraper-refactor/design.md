# Transactional Event Scraper Refactor - Design

## Overview

This design refactors the transactional event scraper to process both QC status logs and form JSON files, enabling complete event records with packet information through event matching and enrichment.

## Architecture

### High-Level Flow

```
1. Discover QC status logs → Create submit events → Store in UnmatchedSubmitEvents
2. Discover JSON files → Extract QC info → Create QC events → Match with submit events
3. On match: Enrich submit event → Push to bucket → Remove from unmatched
4. On match (PASS): Also push QC event to bucket
5. On no match: Log warning about unmatched QC event
6. At completion: Log warning if unmatched submit events remain
```

### Component Structure

```
EventScraper (orchestrator)
├── SubmitEventProcessor (processes QC logs)
│   ├── extract_event_from_log()
│   └── EventGenerator.create_submission_event()
├── QCEventProcessor (processes JSON files)
│   ├── VisitMetadataExtractor.from_json_file_metadata() [from event_capture.visit_extractor]
│   ├── find_qc_status_for_json_file()
│   └── EventGenerator.create_qc_event()
├── UnmatchedSubmitEvents (matching data structure)
│   ├── add()
│   ├── find_and_remove()
│   └── get_remaining()
└── EventCapture (pushes to S3)
```

## Data Models

### EventMatchKey

Matching key for correlating submit and QC events.

```python
class EventMatchKey(BaseModel):
    """Key for matching submit events with QC events.
    
    Uses only fields guaranteed to be in QC status log filename.
    """
    ptid: str
    date: date  # visit date
    module: str
    
    @classmethod
    def from_visit_metadata(cls, metadata: VisitMetadata) -> "EventMatchKey":
        """Create match key from visit metadata."""
        return cls(
            ptid=metadata.ptid,
            date=metadata.date,
            module=metadata.module
        )
```

### UnmatchedSubmitEvents

Collection for managing unmatched submit events with efficient lookup.

```python
class UnmatchedSubmitEvents:
    """Manages unmatched submit events with efficient lookup by match key."""
    
    def __init__(self):
        # Dict[EventMatchKey, VisitEvent]
        self._events: Dict[EventMatchKey, VisitEvent] = {}
    
    def add(self, event: VisitEvent) -> None:
        """Add an unmatched submit event."""
        key = EventMatchKey(
            ptid=event.ptid,
            date=event.visit_date,
            module=event.module
        )
        self._events[key] = event
    
    def find_and_remove(self, key: EventMatchKey) -> Optional[VisitEvent]:
        """Find and remove a submit event by match key.
        
        Returns:
            The matched submit event, or None if not found
        """
        return self._events.pop(key, None)
    
    def get_remaining(self) -> List[VisitEvent]:
        """Get all remaining unmatched submit events."""
        return list(self._events.values())
    
    def count(self) -> int:
        """Get count of unmatched submit events."""
        return len(self._events)
```

### QCEventData

Data extracted from JSON file for creating QC events.

```python
class QCEventData(BaseModel):
    """Data extracted from JSON file for QC event creation."""
    
    visit_metadata: VisitMetadata  # From JSON file (includes packet)
    qc_status: QCStatus  # From QC status log
    qc_completion_timestamp: datetime  # From QC status log modified time
```

## Component Design

### 1. SubmitEventProcessor

Processes QC status logs to create submit events.

```python
class SubmitEventProcessor:
    """Processes QC status logs to create submit events."""
    
    def __init__(
        self,
        project: ProjectAdaptor,
        event_generator: EventGenerator,
        unmatched_events: UnmatchedSubmitEvents,
        date_filter: Optional[DateRange] = None
    ):
        self._project = project
        self._event_generator = event_generator
        self._unmatched_events = unmatched_events
        self._date_filter = date_filter
    
    def process_qc_logs(self) -> None:
        """Discover and process all QC status logs."""
        log_files = self._discover_qc_logs()
        log.info(f"Discovered {len(log_files)} QC status log files")
        
        for log_file in log_files:
            try:
                self._process_log_file(log_file)
            except Exception as error:
                log.error(
                    f"Error processing {log_file.name}: {error}",
                    exc_info=True
                )
    
    def _process_log_file(self, log_file: FileEntry) -> None:
        """Process a single QC status log file."""
        # Apply date filter
        if self._date_filter and not self._date_filter.includes_file(log_file.created):
            log.debug(f"Skipping {log_file.name} - outside date range")
            return
        
        # Extract event data from log
        event_data = extract_event_from_log(log_file)
        if not event_data:
            log.warning(f"Failed to extract event data from {log_file.name}")
            return
        
        # Create submit event
        submit_event = self._event_generator.create_submission_event(event_data)
        if not submit_event:
            log.warning(f"Failed to create submit event from {log_file.name}")
            return
        
        # Add to unmatched collection
        self._unmatched_events.add(submit_event)
        log.debug(
            f"Created submit event for {submit_event.ptid} "
            f"{submit_event.visit_date} {submit_event.module}"
        )
    
    def _discover_qc_logs(self) -> List[FileEntry]:
        """Discover all QC status log files in the project."""
        log_files = []
        for file in self._project.files:
            if file.name.endswith("_qc-status.log"):
                log_files.append(file.reload())
        return log_files
```

### 2. QCEventProcessor

Processes JSON files to create QC events and match with submit events.

```python
class QCEventProcessor:
    """Processes JSON files to create and match QC events."""
    
    def __init__(
        self,
        project: ProjectAdaptor,
        event_generator: EventGenerator,
        unmatched_events: UnmatchedSubmitEvents,
        event_capture: Optional[VisitEventCapture],
        dry_run: bool = False,
        date_filter: Optional[DateRange] = None
    ):
        self._project = project
        self._event_generator = event_generator
        self._unmatched_events = unmatched_events
        self._event_capture = event_capture
        self._dry_run = dry_run
        self._date_filter = date_filter
        self._error_log_template = ErrorLogTemplate()
    
    def process_json_files(self) -> None:
        """Discover and process all JSON files."""
        json_files = self._discover_json_files()
        log.info(f"Discovered {len(json_files)} JSON files")
        
        for json_file in json_files:
            try:
                self._process_json_file(json_file)
            except Exception as error:
                log.error(
                    f"Error processing {json_file.name}: {error}",
                    exc_info=True
                )
    
    def _process_json_file(self, json_file: FileEntry) -> None:
        """Process a single JSON file."""
        # Apply date filter
        if self._date_filter and not self._date_filter.includes_file(json_file.created):
            log.debug(f"Skipping {json_file.name} - outside date range")
            return
        
        # Extract QC event data
        qc_event_data = self._extract_qc_event_data(json_file)
        if not qc_event_data:
            log.debug(f"No QC event data for {json_file.name}")
            return
        
        # Create match key
        match_key = EventMatchKey.from_visit_metadata(
            qc_event_data.visit_metadata
        )
        
        # Try to find matching submit event
        submit_event = self._unmatched_events.find_and_remove(match_key)
        
        if submit_event:
            # Match found - enrich and push submit event
            self._enrich_and_push_submit_event(submit_event, qc_event_data)
            
            # If QC passed, also push QC event
            if qc_event_data.qc_status == "PASS":
                self._push_qc_event(qc_event_data)
        else:
            # No match - log warning
            log.warning(
                f"Unmatched QC event (no corresponding submit event): "
                f"ptid={match_key.ptid}, date={match_key.date}, "
                f"module={match_key.module}, status={qc_event_data.qc_status}"
            )
    
    def _extract_qc_event_data(
        self, json_file: FileEntry
    ) -> Optional[QCEventData]:
        """Extract QC event data from JSON file."""
        # Extract visit metadata from JSON file (includes packet)
        # Note: VisitMetadataExtractor is imported from event_capture.visit_extractor
        visit_metadata = VisitMetadataExtractor.from_json_file_metadata(json_file)
        if not visit_metadata:
            return None
        
        if not VisitMetadataExtractor.is_valid_for_event(visit_metadata):
            return None
        
        # Find corresponding QC status log
        qc_log_file = self._find_qc_status_for_json_file(json_file)
        if not qc_log_file:
            log.debug(f"No QC status log found for {json_file.name}")
            return None
        
        # Extract QC status
        qc_model = FileQCModel.create(qc_log_file)
        qc_status = qc_model.get_file_status()
        
        return QCEventData(
            visit_metadata=visit_metadata,
            qc_status=qc_status,
            qc_completion_timestamp=qc_log_file.modified
        )
    
    def _find_qc_status_for_json_file(
        self, json_file: FileEntry
    ) -> Optional[FileEntry]:
        """Find QC status log for JSON file using ErrorLogTemplate."""
        if not json_file.info:
            return None
        
        forms_json = json_file.info.get("forms", {}).get("json", {})
        if not forms_json:
            return None
        
        module = forms_json.get("module")
        if not module:
            return None
        
        # Generate expected QC log filename
        qc_log_name = self._error_log_template.instantiate(
            record=forms_json, module=module
        )
        if not qc_log_name:
            return None
        
        # Look up in project files
        try:
            return self._project.get_file(qc_log_name)
        except Exception:
            return None
    
    def _enrich_and_push_submit_event(
        self,
        submit_event: VisitEvent,
        qc_event_data: QCEventData
    ) -> None:
        """Enrich submit event with QC data and push to bucket."""
        # Enrich: replace None values with QC event data
        if submit_event.packet is None:
            submit_event.packet = qc_event_data.visit_metadata.packet
        
        if submit_event.visit_number is None:
            submit_event.visit_number = qc_event_data.visit_metadata.visitnum
        
        # Push enriched submit event
        if self._dry_run:
            log.info(
                f"[DRY RUN] Would push enriched submit event: "
                f"{submit_event.ptid} {submit_event.visit_date} "
                f"{submit_event.module} (packet={submit_event.packet})"
            )
        elif self._event_capture:
            self._event_capture.capture_event(submit_event)
            log.info(
                f"Pushed enriched submit event: {submit_event.ptid} "
                f"{submit_event.visit_date} {submit_event.module}"
            )
    
    def _push_qc_event(self, qc_event_data: QCEventData) -> None:
        """Create and push QC pass event."""
        qc_event = self._event_generator.create_qc_event(qc_event_data)
        if not qc_event:
            log.warning("Failed to create QC event")
            return
        
        if self._dry_run:
            log.info(
                f"[DRY RUN] Would push QC pass event: "
                f"{qc_event.ptid} {qc_event.visit_date} {qc_event.module}"
            )
        elif self._event_capture:
            self._event_capture.capture_event(qc_event)
            log.debug(
                f"Pushed QC pass event: {qc_event.ptid} "
                f"{qc_event.visit_date} {qc_event.module}"
            )
    
    def _discover_json_files(self) -> List[FileEntry]:
        """Discover all JSON files in project acquisitions."""
        json_files = []
        
        # Iterate through project hierarchy: subjects -> sessions -> acquisitions
        for subject in self._project.subjects():
            for session in subject.sessions():
                for acquisition in session.acquisitions():
                    for file in acquisition.files:
                        if file.name.endswith(".json"):
                            json_files.append(file.reload())
        
        return json_files
```

### 3. EventGenerator Updates

Add method to create QC events (not just pass-qc events).

```python
class EventGenerator:
    """Creates VisitEvent objects from extracted data."""
    
    # ... existing methods ...
    
    def create_qc_event(
        self, qc_event_data: QCEventData
    ) -> Optional[VisitEvent]:
        """Create a QC event from QC event data.
        
        Creates events for ALL QC statuses (PASS, FAIL, ERROR, etc.)
        but only PASS events should be pushed to bucket.
        
        Args:
            qc_event_data: The QC event data
        
        Returns:
            VisitEvent for QC action, or None if creation fails
        """
        if not self._pipeline_label or self._pipeline_adcid is None:
            log.warning("Cannot create QC event: missing project metadata")
            return None
        
        if self._pipeline_label.datatype is None:
            log.warning(
                f"Pipeline project label should include a datatype: "
                f"{self._project.label}"
            )
            return None
        
        try:
            return VisitEvent(
                action=ACTION_PASS_QC,  # Action is always pass-qc
                study=self._pipeline_label.study_id,
                pipeline_adcid=self._pipeline_adcid,
                project_label=self._project.label,
                center_label=self._project.group,
                gear_name="transactional-event-scraper",
                ptid=qc_event_data.visit_metadata.ptid,
                visit_date=qc_event_data.visit_metadata.date,
                visit_number=qc_event_data.visit_metadata.visitnum,
                datatype=self._pipeline_label.datatype,
                module=qc_event_data.visit_metadata.module,
                packet=qc_event_data.visit_metadata.packet,
                timestamp=qc_event_data.qc_completion_timestamp,
            )
        except ValidationError as error:
            log.warning(f"Failed to create QC event: {error}")
            return None
```

### 4. EventScraper Orchestrator

Updated orchestrator to coordinate both processors.

```python
class EventScraper:
    """Main orchestrator for event scraping."""
    
    def __init__(
        self,
        project: ProjectAdaptor,
        event_capture: Optional[VisitEventCapture] = None,
        dry_run: bool = False,
        date_filter: Optional[DateRange] = None,
    ):
        self._project = project
        self._event_capture = event_capture
        self._dry_run = dry_run
        self._date_filter = date_filter
        
        # Shared components
        self._event_generator = EventGenerator(project)
        self._unmatched_events = UnmatchedSubmitEvents()
        
        # Processors
        self._submit_processor = SubmitEventProcessor(
            project=project,
            event_generator=self._event_generator,
            unmatched_events=self._unmatched_events,
            date_filter=date_filter
        )
        
        self._qc_processor = QCEventProcessor(
            project=project,
            event_generator=self._event_generator,
            unmatched_events=self._unmatched_events,
            event_capture=event_capture,
            dry_run=dry_run,
            date_filter=date_filter
        )
    
    def scrape_events(self) -> None:
        """Execute the scraping process."""
        log.info("Starting event scraping")
        
        # Phase 1: Process QC logs to create submit events
        log.info("Phase 1: Processing QC status logs")
        self._submit_processor.process_qc_logs()
        log.info(
            f"Created {self._unmatched_events.count()} submit events "
            f"awaiting enrichment"
        )
        
        # Phase 2: Process JSON files to create and match QC events
        log.info("Phase 2: Processing JSON files and matching events")
        self._qc_processor.process_json_files()
        
        # Phase 3: Report unmatched submit events
        remaining = self._unmatched_events.get_remaining()
        if remaining:
            log.warning(
                f"Processing complete with {len(remaining)} unmatched submit "
                f"events (no corresponding JSON/QC data found)"
            )
            # Log sample of unmatched events for investigation
            for event in remaining[:5]:  # Log first 5
                log.warning(
                    f"  Unmatched: ptid={event.ptid}, date={event.visit_date}, "
                    f"module={event.module}"
                )
            if len(remaining) > 5:
                log.warning(f"  ... and {len(remaining) - 5} more")
        else:
            log.info("Processing complete: all submit events matched and enriched")
```

## Correctness Properties

### Property 1: Event Matching Correctness
**Validates: Requirements 3.3, 3.4**
**Test Type: Property-based test (if needed)**

For any submit event S and QC event Q:
- If S.ptid == Q.ptid AND S.date == Q.date AND S.module == Q.module, then they match
- When matched, enriched S has Q's packet and visitnum (if S's were None)
- Enriched S preserves original non-None values

**Validation:** Verify in sandbox by checking logs for successful matches and inspecting enriched events in S3.

### Property 2: No Data Duplication
**Validates: Requirements 3.5, 3.6**
**Test Type: Unit test (if needed)**

For any matched pair (submit event S, QC event Q):
- Enriched submit event S is pushed to bucket exactly once
- If Q.status == PASS, QC event Q is pushed to bucket exactly once
- If Q.status != PASS, QC event Q is not pushed to bucket
- The same submit event is never pushed multiple times (even if multiple QC events match)
- The same QC event never causes multiple pushes

**Rationale:** This property ensures we don't create duplicate events in the S3 bucket. Since `find_and_remove()` removes the submit event from the unmatched collection after first match, subsequent QC events with the same match key won't find it again. Each QC event is processed exactly once, so each can push at most one QC event to the bucket.

**Validation:** Verify in sandbox by checking S3 bucket for duplicate events with same identifiers.

### Property 3: Unmatched Event Logging
**Validates: Requirements 3.7, 4.1, 4.2**
**Test Type: Sandbox validation**

For any QC event Q without matching submit event:
- Warning is logged with Q's identifying information (ptid, date, module, status)
- Q is not pushed to event bucket

**Validation:** Check logs for unmatched QC event warnings during sandbox run.

### Property 4: Unmatched Submit Event Reporting
**Validates: Requirements 3.8, 4.3**
**Test Type: Sandbox validation**

At completion:
- If unmatched submit events remain, warning is logged with count
- Sample of unmatched events is logged with identifying information

**Validation:** Check completion logs for unmatched submit event warnings during sandbox run.

### Property 5: Event Enrichment Idempotency
**Validates: Requirements 3.4**
**Test Type: Unit test (if needed)**

For any submit event S and QC event data Q, the enrichment operation is idempotent:
- If S.packet is not None before enrichment, then S.packet remains unchanged after enrichment
- If S.packet is None before enrichment, then S.packet = Q.packet after enrichment
- If S.visitnum is not None before enrichment, then S.visitnum remains unchanged after enrichment  
- If S.visitnum is None before enrichment, then S.visitnum = Q.visitnum after enrichment
- All other fields in S remain unchanged

**Formally:**
```
enrich(S, Q) where S.field != None => S.field (unchanged)
enrich(S, Q) where S.field == None => S.field = Q.field (enriched)
```

**Rationale:** This property ensures that enrichment only fills in missing data and never overwrites existing data. This is important because:
1. Submit events from QC logs may already have some fields populated (from custom info)
2. We want to preserve the "source of truth" from the original submit event
3. QC event data is used only to fill gaps, not to replace existing information

**Validation:** Verify in sandbox by inspecting enriched events in S3 - check that packet values are present and reasonable.

## Testing Strategy

**Approach:** Code-first with minimal testing. Primary validation will be done by running on live sandbox data.

### Minimal Unit Tests (Optional)

Only if issues arise during sandbox testing:

1. **UnmatchedSubmitEvents Tests** (Property 2)
   - Test add/find_and_remove operations
   - Test that second match attempt returns None

2. **Enrichment Logic Tests** (Property 5)
   - Test enrichment preserves non-None values
   - Test enrichment fills None values

### Sandbox Validation (Primary Testing)

Run on live sandbox system to validate:
- Submit events are enriched with packet information
- Pass-QC events are created correctly
- Unmatched events are logged appropriately
- No duplicate events in S3 bucket
- Processing completes without errors

### Property-Based Test (If Needed)

Only implement if sandbox testing reveals matching issues:

1. **Matching Correctness Property** (Property 1)
   - Generate random submit and QC events
   - Verify matching logic correctness across many inputs

## Migration Strategy

### Phase 1: Add New Components
- Add EventMatchKey model
- Add UnmatchedSubmitEvents class
- Add QCEventData model
- Add QCEventProcessor class
- Update EventGenerator with create_qc_event

### Phase 2: Refactor EventScraper
- Split current logic into SubmitEventProcessor
- Update EventScraper to orchestrate both processors
- Maintain backward compatibility with existing behavior

### Phase 3: Update Tests
- Add unit tests for new components
- Add integration tests for matching logic
- Add property-based tests

### Phase 4: Deploy and Monitor
- Deploy to test environment
- Monitor logs for unmatched events
- Verify packet information in captured events

## Backward Compatibility

- Maintains support for date range filtering
- Maintains support for dry-run mode
- Handles files without packet information gracefully
- Processes files in any order
- Continues processing on individual file failures

## Performance Considerations

- Use dictionary for O(1) event lookup by match key
- Process files in streaming fashion (don't load all into memory)
- Reload files only when needed for full metadata
- Log at appropriate levels to avoid excessive logging

## Error Handling

- Continue processing on individual file failures
- Log errors with sufficient context (file name, identifying info)
- Validate data models before creating events
- Handle missing QC logs gracefully
- Handle missing JSON files gracefully

## Logging Strategy

### Info Level
- Phase transitions (starting QC log processing, JSON processing)
- Successful event matching and enrichment
- Completion summary

### Warning Level
- Unmatched QC events (potential data loss)
- Unmatched submit events at completion (incomplete data)
- Failed event creation

### Debug Level
- Individual file processing
- Event creation details
- Skipped files (date filter)

### Error Level
- File processing exceptions
- Unexpected errors
