# nacc-common: High-Level Data Access Functions

## Context

The `nacc-common` package (currently v3.0.0) is used by the [NACC Data Platform demo scripts](https://github.com/naccdata/data-platform-demos) to help Alzheimer's Disease Research Centers interact with the NACC Data Platform, which is built on Flywheel.

Centers use these demos as templates for their own automation scripts. We want to **minimize direct Flywheel SDK coupling** in center-facing code so that a future platform migration doesn't break every center's scripts. `nacc-common` is the abstraction layer — centers should depend on it, not on `flywheel-sdk` directly.

### What works well today

The existing high-level functions in `error_data.py` establish the right pattern:

```python
def get_error_data(project: Project, modules: Optional[set[str]] = None) -> list[dict[str, Any]]
def get_status_data(project: Project, modules: Optional[set[str]] = None) -> list[dict[str, Any]]
```

These take a Flywheel `Project`, hide all the visitor/QC-model machinery internally, and return plain dicts. Centers never touch `FileQCModel`, `GearQCModel`, `ValidationModel`, or `FileEntry` directly. This is the pattern we want to extend.

### What's missing

There are several capabilities already implemented in `nacc-common` internals that are not exposed through similarly simple functions. Centers either can't access them at all, or would have to work directly with Flywheel objects and the visitor hierarchy to use them.

## Requested Changes

### 1. Add PTID filtering to `get_error_data` and `get_status_data`

`ProjectReportVisitor` already accepts a `ptid_set` parameter, but the public functions in `error_data.py` don't expose it.

**Current signatures:**
```python
def get_error_data(project: Project, modules: Optional[set[str]] = None) -> list[dict[str, Any]]
def get_status_data(project: Project, modules: Optional[set[str]] = None) -> list[dict[str, Any]]
```

**Requested signatures:**
```python
def get_error_data(
    project: Project,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> list[dict[str, Any]]

def get_status_data(
    project: Project,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> list[dict[str, Any]]
```

The `ptids` parameter should be passed through to `ProjectReportVisitor` as `ptid_set`. This is a backward-compatible addition.

### 2. Add per-file QC summary function

`FileQCModel.create(file_entry)` and the gear/validation model hierarchy are powerful but require centers to work with Flywheel `FileEntry` objects and understand the internal QC model structure.

**Requested function** (in `error_data.py` or a new module):

```python
def get_file_qc_summary(project: Project, filename: str) -> Optional[dict[str, Any]]
```

**Behavior:**
- Find the named file in `project.files`
- Build a `FileQCModel` from it
- Return a plain dict with:
  - `"filename"`: the filename
  - `"overall_status"`: the result of `FileQCModel.get_file_status()` (PASS/FAIL/IN REVIEW)
  - `"stages"`: a dict mapping gear name → `{"status": QCStatus, "error_count": int}`
- Return `None` if the file is not found or has no QC data

This gives centers a simple way to check "what happened to my file?" without touching any Flywheel or QC model objects.

### 3. Add per-file error detail function

**Requested function:**

```python
def get_file_errors(project: Project, filename: str) -> list[dict[str, Any]]
```

**Behavior:**
- Find the named file in `project.files`
- Build a `FileQCModel` from it
- For each gear, collect errors from `gear_model.get_errors()`
- Return a flat list of dicts, each containing:
  - `"stage"`: the gear name
  - All fields from `FileError.model_dump(by_alias=True)` (type, code, message, location, etc.)
- Return an empty list if the file is not found or has no errors

### 4. Add per-file visit metadata function

`DataIdentification.from_visit_info(file_entry)` reads visit metadata from a file's `.info.visit` dict, but requires a `FileEntry` object.

**Requested function:**

```python
def get_file_visit_metadata(project: Project, filename: str) -> Optional[dict[str, Any]]
```

**Behavior:**
- Find the named file in `project.files`
- Call `DataIdentification.from_visit_info(file_entry)`
- If successful, return `data_id.model_dump()` (the flattened serialization that `DataIdentification` already provides)
- Return `None` if the file is not found or has no visit metadata

### 5. Add project file listing function

Centers currently have to iterate `project.files` directly and parse filenames to understand what's in a project. A convenience function would help.

**Requested function:**

```python
def list_project_files(
    project: Project,
    modules: Optional[set[str]] = None,
    ptids: Optional[set[str]] = None,
) -> list[dict[str, Any]]
```

**Behavior:**
- Iterate QC status log files in the project (files matching the `QC_FILENAME_PATTERN` from `qc_report.py`)
- Apply module and ptid filters (same logic as `ProjectReportVisitor.__should_process_file`)
- For each matching file, extract visit keys via `extract_visit_keys()` and include `FileQCModel.get_file_status()`
- Return a list of dicts, each containing:
  - `"filename"`: the filename
  - `"ptid"`, `"date"`, `"module"`: extracted from the filename
  - `"overall_status"`: the file's aggregate QC status (PASS/FAIL/IN REVIEW), or `None` if no QC data

## Design Notes

### Return types

All functions should return plain `dict`/`list[dict]` — not Pydantic models, not Flywheel objects. This keeps the interface serialization-friendly and avoids leaking internal types to centers.

### The `Project` parameter

All functions currently take a Flywheel `Project`. This is acceptable for now since `get_project()` in `pipeline.py` already creates it. Long-term, if the platform changes, these functions are the seam where a protocol or adapter pattern could be introduced — the call sites in center scripts wouldn't change.

### Backward compatibility

- Changes to `get_error_data` and `get_status_data` add optional parameters only — fully backward compatible.
- New functions are purely additive.
- No existing behavior should change.

### Testing considerations

The new functions wrap existing tested internals (`FileQCModel.create`, `extract_visit_keys`, `ProjectReportVisitor`). Unit tests should mock the Flywheel `Project` and `FileEntry` objects to verify:
- Correct filtering by module and ptid
- Correct dict structure in return values
- `None`/empty-list returns for missing files or absent QC data

## Usage in Demos

Once these functions are available in `nacc-common`, the demo repo will:

1. Add `--module` and `--ptid` CLI flags to `pull_errors.py` and `pull_status.py`
2. Create a new `demo/file_status/` demo that calls `get_file_qc_summary` and `get_file_errors` to inspect individual submissions
3. Create a new `demo/list_files/` demo that calls `list_project_files` to show what's in a project
4. Potentially create enrollment-specific demos using `datatype="enrollment"`

All of these would use only `nacc-common` public functions + `flywheel.Client` for auth — no direct Flywheel object manipulation.
