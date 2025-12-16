# Event logging test scenarios

The purpose of this file is to document the design of tests for the EventAccumulator class and supporting code.

## Implementation Context

### EventAccumulator Overview
- **Location**: `gear/form_scheduler/src/python/form_scheduler_app/visitor_event_accumulator.py`
- **Purpose**: Logs `pass-qc` and `not-pass-qc` events after pipeline completion by reading QC-status files
- **Integration**: Called by `FormSchedulerQueue._log_pipeline_events()` after each pipeline completes
- **Data Source**: Reads `file.info.qc` metadata using `FileQCModel` structure from nacc-common
- **Events**: Only handles outcome events (`pass-qc`, `not-pass-qc`). Submit events are handled by separate submission-logger gear.
- **Scope**: This document focuses only on testing the EventAccumulator in form-scheduler, not the submission-logger gear.

### Pipeline Integration Point
```python
# In FormSchedulerQueue._process_pipeline_queue()
JobPoll.wait_for_pipeline(self.__proxy, job_search)  # Pipeline completes
self._log_pipeline_events(file=file, pipeline=pipeline)  # EventAccumulator called here
```

### File Structure and Locations
- **CSV files**: PROJECT level (input files, tagged for processing)
- **JSON files**: ACQUISITION level (pipeline outputs, one per visit)
- **QC-status files**: PROJECT level (contain `file.info.qc` metadata)
- **Config files**: PROJECT level (pipeline configuration files)

## Data Model: FileQCModel Structure

The EventAccumulator reads QC metadata from `file.info.qc` using the `FileQCModel` structure. Based on real examples:

### Example 1: Pipeline Success (All Gears PASS)
```json
{
  "qc": {
    "identifier-lookup": {
      "validation": {
        "data": [],
        "cleared": [],
        "state": "PASS"
      }
    },
    "form-transformer": {
      "validation": {
        "data": [],
        "cleared": [],
        "state": "PASS"
      }
    },
    "form-qc-checker": {
      "validation": {
        "data": [],
        "cleared": [],
        "state": "PASS"
      }
    },
    "form-qc-coordinator": {
      "validation": {
        "data": [],
        "cleared": [],
        "state": "PASS"
      }
    }
  }
}
```

### Example 2: Pipeline Failure (form-qc-checker FAIL)
```json
{
  "qc": {
    "identifier-lookup": {
      "validation": {
        "data": [],
        "cleared": [],
        "state": "PASS"
      }
    },
    "form-transformer": {
      "validation": {
        "data": [],
        "cleared": [],
        "state": "PASS"
      }
    },
    "form-qc-checker": {
      "validation": {
        "data": [
          {
            "timestamp": "2025-08-22 12:10:25",
            "type": "alert",
            "code": "b5-ivp-p-1010",
            "location": {
              "key_path": "anx"
            },
            "container_id": "68a85b2b481d892240473d0e",
            "flywheel_path": "fw://dummy-center/ingest-form/NACC100001/FORMS-VISIT-4F/UDS/NACC100001_FORMS-VISIT-4F_UDS.json",
            "value": "0",
            "expected": null,
            "message": "if q6a. anx (anxiety) = 0 (no), then form b9, q12c. beanx (anxiety) should not equal 1 (yes)",
            "ptid": "ADRC1001",
            "visitnum": "4F",
            "date": "2025-08-22",
            "naccid": "NACC100001"
          }
        ],
        "cleared": [],
        "state": "FAIL"
      }
    }
  }
}
```

### Example 3: Cleared Alerts (Count as PASS)
```json
{
  "qc": {
    "form-qc-checker": {
      "validation": {
        "data": [
          {
            "timestamp": "2025-11-04 13:19:13",
            "type": "alert",
            "code": "d1b-i4vp-p-1005",
            "location": {
              "key_path": "csfad"
            },
            "message": "if q6b. amylcsf or q6f. csftau at previous visit = 1, then q4a. csfad should =1",
            "ptid": "ADRC1000",
            "visitnum": "3F",
            "date": "2025-03-19",
            "naccid": "NACC100000"
          }
        ],
        "cleared": [
          {
            "alertHash": "3368b32006e31d830873b687f66e6c42f352ccf714c342f984d6bbef0e71ac2b",
            "clear": true,
            "finalized": true,
            "provenance": [
              {
                "user": "user@dummy.org",
                "clearSetTo": true,
                "timestamp": "20251104085231"
              }
            ]
          }
        ],
        "state": "PASS"
      }
    }
  }
}
```

## Pipeline Context

### Submission Pipeline
- **Input**: CSV files tagged with `queued` at PROJECT level
- **Process**: `nacc-file-validator` → `identifier-lookup` → `form-transformer`
- **Output**: JSON files at ACQUISITION level (one per visit/row in CSV)
- **QC Files**: QC-status files created at PROJECT level with metadata from each gear

### Finalization Pipeline  
- **Input**: JSON files tagged with `submission-completed` at ACQUISITION level
- **Process**: `form-qc-coordinator` → `form-qc-checker`
- **Output**: Finalized data with QC validation
- **QC Files**: Additional QC-status files with finalization metadata

## Test Scenarios

### Scenario 1: Single Visit - Pipeline Success
**Description**: One visit passes through entire submission pipeline successfully

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (1 row, processed by pipeline)
  - `adrc1000_2025-03-19_uds_qc-status.log` (QC metadata with all gears PASS)
- ACQUISITION level:
  - `NACC100000_FORMS-VISIT-3F_UDS.json` (pipeline output)

**QC Metadata**: All gears show `state: "PASS"` (identifier-lookup, form-transformer)

**Expected Event**: `pass-qc` event with gear name "form-transformer" (final gear), ptid="ADRC1000", visitnum="3F", date="2025-03-19"

### Scenario 2: Single Visit - Pipeline Failure at Early Stage
**Description**: Visit fails at form-transformer, pipeline stops

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (1 row, processed by pipeline)
  - `adrc1001_2025-08-22_uds_qc-status.log` (QC metadata with form-transformer FAIL)
- ACQUISITION level: (no JSON file - pipeline failed)

**QC Metadata**: 
- `identifier-lookup`: `state: "PASS"`
- `form-transformer`: `state: "FAIL"` with error details

**Expected Event**: `not-pass-qc` event with error from form-transformer, ptid="ADRC1001", visitnum="4F", date="2025-08-22"

### Scenario 3: Single Visit - Pipeline Failure at Late Stage
**Description**: Visit passes early gears but fails at form-qc-checker

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (1 row, processed by pipeline)
  - `adrc1001_2025-08-22_uds_qc-status.log` (mixed PASS/FAIL states)
- ACQUISITION level:
  - `NACC100001_FORMS-VISIT-4F_UDS.json` (created before failure)

**QC Metadata**: 
- `identifier-lookup`: `state: "PASS"`
- `form-transformer`: `state: "PASS"`
- `form-qc-checker`: `state: "FAIL"` with alert errors (b5-ivp-p-1010, d1b-i4vp-p-1004, etc.)

**Expected Event**: `not-pass-qc` event with first error from form-qc-checker, ptid="ADRC1001", visitnum="4F", date="2025-08-22"

### Scenario 4: Multiple Visits - Mixed Outcomes
**Description**: CSV with multiple visits, some pass, some fail at different stages

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (3 rows)
  - `adrc1000_2025-03-19_uds_qc-status.log` (PASS with cleared alerts)
  - `adrc1001_2025-08-22_uds_qc-status.log` (FAIL at form-qc-checker)
  - `adrc1003_2025-10-15_uds_qc-status.log` (FAIL at form-qc-checker with error)
- ACQUISITION level:
  - `NACC100000_FORMS-VISIT-3F_UDS.json` (success case)
  - `NACC153815_FORMS-VISIT-4F_UDS.json` (created before late failure)
  - `NACC100001_FORMS-VISIT-3F_UDS.json` (created before late failure)

**QC Metadata Examples**:
- Visit 1 (ADRC1000): Submission pipeline - all gears PASS (identifier-lookup, form-transformer)
- Visit 2 (ADRC1001): Finalization pipeline - form-qc-checker FAIL with multiple alerts (b5-ivp-p-1010, d1b-i4vp-p-1004, etc.)
- Visit 3 (ADRC1003): Finalization pipeline - form-qc-checker FAIL with both alerts and errors (c2-ivp-m-185 error)

**Expected Events**: 
- One `pass-qc` event for ADRC1000 (visitnum="3F", date="2025-03-19")
- Two `not-pass-qc` events for ADRC1001 (visitnum="4F") and ADRC1003 (visitnum="3F", date="2025-10-15")

### Scenario 5: File Timestamp Filtering
**Description**: Test that only QC-status files modified after input file are processed

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (created at timestamp T)
  - `adrc1000_2025-03-19_uds_qc-status.log` (modified at T-1, should be ignored)
  - `adrc1002_2025-06-18_uds_qc-status.log` (modified at T+1, should be processed)

**QC Metadata**: 
- ADRC1002 file contains finalization pipeline results with form-qc-checker PASS with cleared alerts (b4-i4vp-p-1015, b9-i4vp-p-1006, etc.)

**Expected Events**: Only one `pass-qc` event for ADRC1002 (visitnum="3F")

### Scenario 6: Finalization Pipeline
**Description**: Test event logging for finalization pipeline processing JSON files

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (original submission input)
  - `adrc1002_2025-06-18_uds_qc-status.log` (finalization QC metadata)
- ACQUISITION level:
  - `NACC274180_FORMS-VISIT-3F_UDS.json` (input to finalization pipeline)

**QC Metadata**: 
- Contains `form-qc-coordinator` and `form-qc-checker` job_info sections
- `form-qc-coordinator`: state="PASS"
- `form-qc-checker`: state="PASS" with cleared alerts

**Expected Event**: `pass-qc` event for ADRC1002 (visitnum="3F") based on finalization pipeline outcome

### Scenario 7: No QC Metadata
**Description**: Test behavior when QC-status files exist but have no relevant metadata

**File Structure**:
- PROJECT level:
  - `input-uds.csv`
  - `adrc1000_2025-03-19_uds_qc-status.log` (empty or malformed `file.info.qc`)

**QC Metadata Variations**:
- Empty `qc` object: `{"qc": {}}`
- Missing gear sections: `{"qc": {"unknown-gear": {...}}}`
- Malformed validation structure: `{"qc": {"form-qc-checker": {"invalid": "structure"}}}`

**Expected Events**: No events logged (graceful handling of missing/invalid metadata)

### Scenario 8: Multiple Modules
**Description**: Test processing files for different modules (UDS, FTLD, etc.)

**File Structure**:
- PROJECT level:
  - `input-uds.csv`, `input-ftld.csv`
  - `adrc1000_2025-03-19_uds_qc-status.log`, `adrc1000_2025-03-19_ftld_qc-status.log`
- ACQUISITION level:
  - `NACC100000_FORMS-VISIT-3F_UDS.json`
  - `NACC100000_FORMS-VISIT-3F_FTLD.json`

**QC Metadata**: 
- UDS file: All gears PASS with cleared alerts
- FTLD file: Similar structure but for FTLD module processing

**Expected Events**: 
- One `pass-qc` event for UDS module (ptid="ADRC1000", visitnum="3F", date="2025-03-19")
- One `pass-qc` event for FTLD module (same ptid/visitnum, different module)

### Scenario 9: Cleared Alerts (Count as Passing)
**Description**: Test that cleared alerts are treated as passing validations

**File Structure**:
- PROJECT level:
  - `input-uds.csv` (original submission input)
  - `adrc1000_2025-03-19_uds_qc-status.log` (has cleared alerts)
- ACQUISITION level:
  - `NACC100000_FORMS-VISIT-3F_UDS.json` (created from CSV processing)

**QC Metadata**: 
- `form-qc-checker`: `state: "PASS"` with both `data` (7 alerts) and `cleared` arrays (7 cleared items)
- All alerts have corresponding cleared entries with `"clear": true, "finalized": true`
- Cleared by user "user@dummy.org" with timestamps

**Expected Event**: `pass-qc` event for ADRC1000 (visitnum="3F", date="2025-03-19") because cleared alerts count as passing

## Mock Data Requirements

### Required Mock Objects
1. **MockProject**: 
   - `get_pipeline_adcid()` method
   - `label` property (for study extraction)
   - `group` property (center label)
   - File listing capabilities

2. **MockFileEntry**:
   - `info.qc` structure matching `FileQCModel`
   - `created` and `modified` timestamps
   - `name` property for file identification

3. **Pipeline Configuration**:
   - Matching current form_scheduler pipeline format
   - Module lists for filtering

4. **VisitEventLogger Mock**:
   - Capture and verify logged events
   - Event assertion helpers

### Test Data Patterns
- **Visit identifiers**: PTID, visit dates, visit numbers
- **Module names**: UDS, FTLD, LBD, etc.
- **Gear names**: Matching actual pipeline gears
- **Timestamps**: Proper sequencing for filtering tests
- **Error structures**: Valid FileError objects with required fields

## Implementation Details

### QC-Status File Naming (ErrorLogTemplate)
Files are named using `ErrorLogTemplate.instantiate()`:
- **Pattern**: `{ptid}_{date}_{module}_qc-status.log`
- **PTID**: Leading zeros stripped (e.g., "0110001" → "110001")
- **Date**: Normalized to YYYY-MM-DD format
- **Module**: Lowercase (e.g., "UDS" → "uds")
- **Example**: `110001_2024-01-15_uds_qc-status.log`

### Event Generation Rules
1. **Cleared alerts**: Count as passing (state effectively becomes "PASS")
2. **Multiple gears**: EventReportVisitor finds first error OR last passing validation
3. **Visit numbers**: Can be made up for test purposes (will come from actual data in practice)

## Questions for Review

1. **Multiple gears per file**: How should events be prioritized when multiple gears have different states?

2. **Error vs Warning handling**: Should warnings generate events or only errors?

3. **Module filtering**: Should EventAccumulator respect pipeline module filters?
