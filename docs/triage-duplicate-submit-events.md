# Triage: Duplicate Submission Events Creating Orphaned "submit" Records

## Issue Summary

When a center resubmits a visit packet without changes, the submission pipeline does not run QC on the duplicate (form-transformer detects it as a duplicate and skips processing). However, identifier-lookup logs a "submit" event with a new timestamp before the duplicate is detected downstream. Since QC never runs, there is no subsequent "pass-qc" event to match the duplicate "submit" event.

These orphaned submit events accumulate in the checkpoint parquet file and appear as unfinalized submissions in reporting.

## Pipeline Flow

```
CSV File Upload
  → identifier-lookup (logs "submit" per row — no duplicate awareness)
  → form-transformer (detects duplicates, drops them — no events logged)
  → form_qc_checker (validates, updates QC metadata — no events logged)
  → form-scheduler (logs "pass-qc" for finalized files that passed QC)
```

## Root Cause

### identifier-lookup: Unconditional "submit" Event Logging

- **File**: `gear/identifier_lookup/src/python/identifier_app/run.py`
- The gear processes every CSV row through an `AggregateCSVVisitor` with `visit_all_strategy`
- A `CSVCaptureVisitor` logs a `"submit"` event for every row unconditionally
- Uses the file's creation timestamp as the event timestamp
- Has no awareness of whether the record is a duplicate of an existing visit

### form-transformer: Duplicate Detection (Downstream, No Events)

- **File**: `gear/form_transformer/src/python/form_csv_app/main.py`
- Calls `FormPreprocessor.is_existing_visit()` which queries the forms store and compares with `is_duplicate_dict()`
- When a true duplicate is found, the record is added to `__existing_visits` and never processed through QC
- **No transactional events are logged** for duplicates
- The gear copies downstream metadata from the previous run but does not signal the event system

### form-scheduler: "pass-qc" Events Only for Finalized Files

- **File**: `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py`
- Only logs `"pass-qc"` when it finds finalized JSON files that passed QC
- Since duplicate submissions never produce new JSON files, no `"pass-qc"` event is created

## S3 Event File Behavior

The event capture writes to S3 with filename format:
```
{env}/log-{action}-{timestamp}-{adcid}-{project}-{ptid}-{visit_date}.json
```

Because `timestamp` comes from the new submission's file creation time, each resubmission produces a **unique S3 file** — they do not overwrite each other. Every duplicate resubmission creates a new orphan `log-submit-*` file.

## Impact on event_log_checkpoint Lambda

### Lambda Role

The `event_log_checkpoint` lambda (`reporting-lambdas/lambda/event_log_checkpoint/`) is a pure accumulator. It:

1. Reads event JSON files from S3
2. Validates them against the `VisitEvent` Pydantic model
3. Writes them into a consolidated Parquet checkpoint file (grouped by study-datatype)

It performs **no event pairing, finalization analysis, or duplicate detection**.

### Deduplication Identity Columns

```python
IDENTITY_COLUMNS = [
    "action",
    "ptid",
    "visit_date",
    "timestamp",      # <-- different for each resubmission
    "datatype",
    "module",
    "pipeline_adcid",
]
```

Because `timestamp` is part of the identity key, each resubmission is treated as a distinct event. The dedup logic only prevents exact duplicate reads from S3.

### What Accumulates in the Parquet Checkpoint

For a visit submitted 3 times (original + 2 duplicate resubmissions):

| action | ptid | visit_date | timestamp | module |
|--------|------|------------|-----------|--------|
| submit | 110001 | 2024-01-15 | 2024-01-15T10:00:00Z | UDS |
| submit | 110001 | 2024-01-15 | 2024-02-01T09:00:00Z | UDS |
| submit | 110001 | 2024-01-15 | 2024-03-15T11:00:00Z | UDS |
| pass-qc | 110001 | 2024-01-15 | 2024-01-15T10:30:00Z | UDS |

Three submit rows, one pass-qc. All preserved as distinct records.

### Reporting Impact

- Any downstream query looking for "submits without a matching pass-qc" for the same `(ptid, visit_date, module)` will find **N-1 false positives** for a visit resubmitted N times
- `query_validation.calculate_submission_timing_metrics()` operates on ALL submit events, inflating timing calculations
- The checkpoint data is consumed by Athena/reporting dashboards where pairing logic runs

## Transactional Event Scraper Behavior

The `transactional_event_scraper` gear (a retroactive batch scraper) uses `EventMatchKey(ptid, date, module)` stored in a `Dict[EventMatchKey, VisitEvent]`. This means:

- Only **one** submit event per `(ptid, date, module)` is stored (latest wins if key collides)
- Unmatched submit events are pushed in Phase 3 without enrichment
- The scraper somewhat masks the issue by deduplicating, but the **live pipeline** does not

## Key Distinction: Why This Is Hard to Solve Without Explicit Signal

The core challenge is distinguishing between these scenarios at the reporting layer:

| Scenario | Events in checkpoint | Should appear in reports? |
|----------|---------------------|--------------------------|
| Duplicate submission (no changes) | `submit` only (no pass-qc, no not-pass-qc) | **No** — safely ignorable |
| Legitimate submission that fails QC | `submit` + `not-pass-qc` | **Yes** — as a QC failure |
| Legitimate submission still in progress | `submit` only (no pass-qc yet) | **Yes** — as unfinalized |

Scenarios 1 and 3 look identical in the checkpoint data: a `submit` event with no matching `pass-qc` or `not-pass-qc`. Without explicit signal from the pipeline, there is no way to reliably distinguish "duplicate that was intentionally dropped" from "legitimate submission that hasn't finished processing yet."

Only form-transformer has the authoritative information to make this distinction, because it is the component that performs the duplicate check. No other component in the pipeline can reliably determine whether a submission is a true duplicate.

## Resolution Options

### Option A: Log a new event type in form-transformer (recommended)

Add a `"duplicate-submit"` event type and have form-transformer log it when it detects an existing visit. This gives the reporting layer explicit signal to distinguish duplicates from legitimately unfinalized submissions.

With this in place, reporting logic becomes deterministic:

- `submit` with no `pass-qc`, no `not-pass-qc`, and no `duplicate-submit` = genuinely unfinalized
- `submit` with a corresponding `duplicate-submit` (same ptid/visit_date/module) = safely ignorable
- `submit` with `not-pass-qc` = QC failure
- `submit` with `pass-qc` = successfully finalized

**Changes required:**

1. **`common/src/python/event_capture/visit_events.py`** — Add `"duplicate-submit"` to `VisitEventType` literal and add `ACTION_DUPLICATE_SUBMIT` constant
2. **`gear/form_transformer/src/python/form_csv_app/main.py`** — Add `VisitEventCapture` dependency injection; log `"duplicate-submit"` in the `is_existing_visit()` branch
3. **Lambda model** (`reporting-lambdas/.../checkpoint_lambda/models.py`) — Add `"duplicate-submit"` to the lambda's `VisitEventType` literal
4. **Lambda S3 retriever** (`s3_retriever.py`) — Update `DEFAULT_PATTERN` regex to include `duplicate-submit`
5. **Reporting queries** — Filter on `action != "duplicate-submit"` for finalization analysis, or use `duplicate-submit` presence to dismiss the corresponding `submit`

**Pros:**
- Explicit and auditable — tracks how many duplicates come in
- Reporting can filter on event type cleanly
- Preserves historical signal for operational monitoring
- Deterministic: no heuristics needed to distinguish duplicates from in-progress submissions

**Cons:**
- Requires changes across multiple components and repos (gears + lambda)
- Requires coordinated deployment

### Option B: Suppress the submit event in identifier-lookup

Give identifier-lookup the ability to detect duplicates before logging the event.

**Pros:** No orphan events ever created.

**Cons:**
- Moves duplicate detection logic upstream, duplicating what form-transformer already does
- Adds latency (forms store query) and coupling to identifier-lookup
- Violates separation of concerns
- **Does not solve the distinguishability problem**: if the duplicate check at identifier-lookup gives a different answer than form-transformer (due to timing, race conditions, or stale data), you either suppress a legitimate submit (false negative in reporting) or fail to suppress a duplicate (same problem as today)
- Only form-transformer has the authoritative answer — it's the component with the forms store query that determines whether the content is truly identical

### Option C: Handle at reporting/query layer (simplest short-term)

Keep only the latest submit event per `(ptid, visit_date, module)` when computing unfinalized counts, or treat a submit as "finalized" if any pass-qc exists for the same key regardless of timestamp.

**Pros:**
- No gear or lambda code changes
- Can be applied purely in Athena queries or dashboard logic
- Immediate fix with no deployment

**Cons:**
- **Cannot reliably distinguish duplicate submissions from legitimately unfinalized ones** — both look like a submit with no matching pass-qc
- Heuristic approaches (e.g., "only count the latest submit per visit") may misclassify legitimate slow-pipeline visits or multiple valid submissions for different packets
- Doesn't provide visibility into duplicate submission volume
- Every downstream consumer needs to implement the same logic
- Fragile: any change to pipeline timing can break the heuristic

## Recommendation

**Short-term**: Apply Option C at the reporting/query layer as a best-effort correction for unfinalized counts. The heuristic "a submit is finalized if any pass-qc exists for the same (ptid, visit_date, module)" will cover the common case but may still misclassify edge cases.

**Long-term**: Implement Option A to add a proper `"duplicate-submit"` event type. This is the only option that gives the system deterministic signal to distinguish duplicates from legitimately unfinalized submissions, because it captures the information at the point where the duplicate determination is actually made (form-transformer).

## Files Referenced

| File | Role |
|------|------|
| `common/src/python/event_capture/visit_events.py` | Defines `VisitEventType` literal and `VisitEvent` model |
| `common/src/python/event_capture/csv_capture_visitor.py` | Per-row submit event capture used by identifier-lookup |
| `common/src/python/event_capture/event_capture.py` | S3 event file writer with filename format |
| `common/src/python/event_capture/models.py` | `EventMatchKey` and `UnmatchedSubmitEvents` |
| `common/src/python/preprocess/preprocessor.py` | `is_existing_visit()` duplicate detection |
| `gear/identifier_lookup/src/python/identifier_app/run.py` | Submit event capture wiring |
| `gear/form_transformer/src/python/form_csv_app/main.py` | Duplicate detection, no event logging |
| `gear/form_scheduler/src/python/form_scheduler_app/event_accumulator.py` | pass-qc event capture |
| `gear/transactional_event_scraper/src/python/.../event_scraper.py` | Batch event scraper |
| `reporting-lambdas/.../checkpoint_lambda/models.py` | Lambda's `VisitEvent` model |
| `reporting-lambdas/.../checkpoint_lambda/checkpoint.py` | `IDENTITY_COLUMNS` and dedup logic |
| `reporting-lambdas/.../checkpoint_lambda/s3_retriever.py` | S3 file pattern regex |
| `reporting-lambdas/.../checkpoint_lambda/query_validation.py` | Analytical query helpers |
