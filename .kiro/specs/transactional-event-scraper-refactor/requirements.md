# Transactional Event Scraper Refactor - Requirements

## Overview

Refactor the transactional event scraper to discover packet information from form JSON files and properly match submission events with QC events. The current implementation only processes QC status log files, which don't contain packet information. This refactor will process both QC status logs and form JSON files to create complete event records.

## Background

### Current Behavior
- Processes only QC status log files (`*_qc-status.log`)
- Creates submission events from log file metadata
- Creates pass-qc events when QC status is PASS
- Missing packet information because it's not available in QC status logs

### Problem
- Packet information is required for complete event records
- Packet is available in form JSON file custom info (`file.info.forms.json.packet`)
- Need to correlate QC events with submission events to enrich the data

## User Stories

### 1. As a data analyst, I need complete event records with packet information
**Acceptance Criteria:**
- 1.1 Submission events include packet information when available
- 1.2 QC events include packet information when available
- 1.3 Events without packet information are still captured (for backward compatibility)

### 2. As a system operator, I need the scraper to process both QC logs and form JSON files
**Acceptance Criteria:**
- 2.1 Scraper discovers and processes QC status log files
- 2.2 Scraper discovers and processes form JSON files
- 2.3 Processing handles files in any order (QC log before JSON or vice versa)
- 2.4 Processing is resilient to missing files (QC log without JSON or JSON without QC log)

### 3. As a developer, I need events to be matched and merged correctly
**Acceptance Criteria:**
- 3.1 Submit events are created from QC status logs with available metadata
- 3.2 QC events are created from form JSON files with QC status information
- 3.3 When a QC event matches a submit event, the submit event is enriched with QC event data
- 3.4 Enriched submit events replace None/missing values with data from QC events
- 3.5 Matched submit events are pushed to the event bucket
- 3.6 Pass-QC events are pushed to the event bucket
- 3.7 Unmatched QC events are logged but not pushed to the bucket
- 3.8 Unmatched submit events remain in the collection for potential future matching

### 4. As a system operator, I need to know when data is being discarded
**Acceptance Criteria:**
- 4.1 Unmatched QC events are logged with identifying information (ptid, date, module)
- 4.2 Warning is logged when QC event cannot be matched to a submit event
- 4.3 At completion, log count of unmatched submit events remaining (potential data loss)

## Functional Requirements

### FR1: Event Discovery
**Priority:** High

The scraper must discover both types of files:
- QC status log files: `*_qc-status.log` at project level
- Form JSON files: `*.json` at acquisition level (within subjects/sessions)

### FR2: Submit Event Creation
**Priority:** High

Submit events are created from QC status log files:
- Extract visit metadata from log file (ptid, date, module, visitnum)
- Use file creation timestamp as submission timestamp
- Packet field will initially be None (to be enriched later)
- Store unmatched submit events for later matching

### FR3: QC Event Creation
**Priority:** High

QC events are created from form JSON files:
- Extract visit metadata from `file.info.forms.json` (ptid, visitdate, module, visitnum, packet)
- Find corresponding QC status log using ErrorLogTemplate pattern
- Extract QC status from QC status log file
- Use QC log modified timestamp as QC completion timestamp
- Create QC events for ALL QC statuses (PASS, FAIL, ERROR, etc.)

### FR4: Event Matching
**Priority:** High

Match QC events with submit events:
- Match on fields guaranteed to be in QC status log filename: ptid, date, module
- When match found:
  - Enrich submit event with QC event data (replace None values)
  - Remove submit event from unmatched collection
  - Push enriched submit event to bucket
  - If QC status is PASS, also push QC event to bucket
- When no match found:
  - Log unmatched QC event with identifying information
  - Do not push unmatched QC event to bucket

### FR5: Event Enrichment
**Priority:** High

When merging QC event data into submit event:
- Replace None/missing values in submit event with values from QC event
- Specifically enrich: packet, visitnum (if missing)
- Preserve existing non-None values in submit event
- Do not modify the QC event itself

### FR6: Unmatched Event Management
**Priority:** Medium

Manage unmatched submit events:
- Store unmatched submit events in a collection
- Allow efficient lookup by matching fields (ptid, date, module)
- Remove events from collection when matched
- Report count of unmatched submit events at completion

### FR7: Logging for Data Loss Detection
**Priority:** High

Log when data might be discarded:
- Log warning when QC event cannot be matched to submit event (include ptid, date, module)
- Log info when submit event is successfully matched and enriched
- At completion, log warning if unmatched submit events remain (include count and sample identifiers)
- Log errors for file processing failures with sufficient context

### FR8: Backward Compatibility
**Priority:** Medium

Maintain compatibility with existing behavior:
- Support date range filtering
- Support dry-run mode
- Handle files without packet information gracefully
- Process files in any order

## Non-Functional Requirements

### NFR1: Performance
- Process files efficiently without loading all into memory
- Use streaming/iterator patterns where possible

### NFR2: Reliability
- Continue processing on individual file failures
- Log errors with sufficient context for debugging
- Validate data models before creating events

### NFR3: Maintainability
- Separate concerns: discovery, extraction, matching, capture
- Use dependency injection for testability
- Follow existing code patterns from form_scheduler

### NFR4: Observability
- Log at appropriate levels (debug, info, warning, error)
- Provide actionable error messages for data loss scenarios
- Include file names and identifying information (ptid, date, module) in logs
- Warn when unmatched events indicate potential data loss

## Technical Constraints

### TC1: Reuse Existing Code
- Borrow JSON file processing logic from form_scheduler
- Use existing VisitMetadataExtractor patterns
- Use ErrorLogTemplate for filename generation
- Maintain existing event models and capture mechanisms

### TC2: Data Models
- Use existing VisitMetadata model
- Use existing VisitEvent model
- Use existing FileQCModel for QC status
- Extend EventData model if needed for matching

### TC3: Matching Fields
Match events on fields guaranteed to be in QC status log filename:
- ptid (required)
- date (required)
- module (required)

Note: visitnum and packet are NOT in the filename, so cannot be used for matching.

## Out of Scope

- Modifying event capture mechanism (S3 bucket structure)
- Changing VisitEvent model structure
- Processing non-form data types
- Historical data migration
- Retroactive enrichment of already-captured events

## Dependencies

- form_scheduler code (for JSON file processing patterns)
- nacc_common.error_models (VisitMetadata, FileQCModel)
- event_capture.visit_events (VisitEvent, ACTION_SUBMIT, ACTION_PASS_QC)
- error_logging.error_logger (ErrorLogTemplate)

## Success Metrics

- All submission events include packet information when available
- QC events are correctly matched with submission events
- No duplicate events are created
- Unmatched QC events are logged with warnings (potential data loss)
- Unmatched submit events are logged at completion (potential incomplete data)
- Processing completes successfully for all files in test projects
