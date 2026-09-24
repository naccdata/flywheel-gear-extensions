# Flywheel Metadata Usage in DataViews and Search Queries

An audit of where ten Flywheel metadata paths are used as **query terms** — DataView columns
and filter expressions, and `find`/`search` query strings — across the six NACC repositories.

The distinction this report draws is between **querying** a metadata path (the path is sent to
Flywheel as part of a DataView filter/column spec or a finder query string) and **reading** it
(the container is fetched first, then the path is walked as a Python dict or JS object key).
Query sites break differently from reads: a renamed or reshaped path silently returns zero rows
rather than raising, so they need to be enumerated exactly.

## Scope and Method

### Repositories surveyed

| Repository | Commit | Notes |
|---|---|---|
| `flywheel-gear-extensions` | `3f91f257` (`feature/add-covid-forms`) | This repo |
| `naccdata/issue-manager` | `d95553e` | Angular/TypeScript, `@flywheel-io/extension` |
| `naccdata/nacc-attribute-deriver` | `2b1fb8f` | No Flywheel SDK dependency |
| `naccdata/user-management` | `c90c8f7` | Includes a vendored `reference-code/common` tree |
| `naccdata/data-platform-admin-tasks` | `459aed4` | |
| `naccdata/nacc-file-validator` | `b22720a` | |

### Paths audited

`file.info.forms`, `file.info.qc`, `file.info.resolved`, `file.info.raw`, `file.info.header`,
`file.info.derived`, `file.info.config`, `project.info.studies`, `project.info.centers`,
`subject.info.derived`.

### What counts as a query site

| Kind | Meaning |
|---|---|
| `dataview filter` | Path appears in a DataView `filter` expression sent to Flywheel |
| `dataview column` | Path appears as a DataView column `data_key` / src |
| `find/search query` | Path appears inside a `.find()`, `.find_first()`, `get_files()` query string |
| `path builder` | A constant or function that assembles such a path for the above |
| `commented out` | A former query site, disabled in source |

Direct reads and writes are excluded from the main sections and summarized in the
[appendix](#appendix-direct-reads-and-writes).

### Method

Grep across all file types (excluding `.git`) in each repo for each path plus its variants, and
for `DataView`, `ViewBuilder`, `make_builder`, `add_column`, `columns=`, `filter=`,
`filter_expression`, `set_filter`, `structured_query`, `find(`, `find_first`, `find_one`,
`finder`, `search(`. Every hit was then read in context to classify it. JS
`Array.prototype.find` hits in `issue-manager` and in `user-management`'s TypeScript components
were excluded as non-Flywheel.

### Caveats

Three call sites accept arbitrary paths from their callers and therefore carry metadata paths
without leaving a greppable literal. A grep-only audit of any repo will miss paths that flow
through them:

| Injection point | Location |
|---|---|
| `get_matching_acquisition_files_info(columns=…, filters=…)` | [flywheel_proxy.py:752](../common/src/python/flywheel_adaptor/flywheel_proxy.py#L752) |
| `get_files(query)` | [flywheel_proxy.py:231](../common/src/python/flywheel_adaptor/flywheel_proxy.py#L231) |
| `subject_adaptor` `self.info.get(module)` — `module` is a runtime variable | `subject_adaptor.py` |

## Coverage Matrix

Counts are **query sites only**. `read` means the path is used, but never in a query.

| Path | gear-extensions | issue-manager | attribute-deriver | user-management | admin-tasks | file-validator |
|---|---|---|---|---|---|---|
| `file.info.forms` | **14** (1 builder, 9 col, 4 filter) | — | read | — | — | — |
| `file.info.qc` | **1 filter** (+2 commented) | 6 (2 builder, 4 col)¹ | — | — | — | indirect² |
| `file.info.resolved` | read | — | read | — | — | — |
| `file.info.raw` | read | — | read | — | — | — |
| `file.info.header` | read | — | read | — | — | — |
| `file.info.derived` | read | — | read | — | — | — |
| `file.info.config` | — | — | — | — | — | — |
| `project.info.studies` | read | — | — | read | read | — |
| `project.info.centers` | read | — | — | read | — | — |
| `subject.info.derived` | read | — | read | — | —³ | — |

¹ Synthetic column keys only — `issue-manager` never issues a real DataView call. See
[file.info.qc](#fileinfoqc).
² Written via `flywheel_gear_toolkit`; the string `file.info.qc` never appears in the source.
³ `data-platform-admin-tasks` has a real DataView on the sibling path `subject.info.enrollment.*`.

## Key Findings

**1. Only two of the ten paths are ever queried.** `file.info.forms.json.*` and
`file.info.qc.*` appear in DataView columns and filters. The other eight are only read or
written after the container is already in memory. `file.info.config` does not appear in any
repo in any role.

**2. `file.info.qc` filtering has been migrated to tags — except in one place.** Two DataView
filters on `file.info.qc.<gear>.validation.state=PASS` were commented out and replaced with
`file.tags=|[<gear>-PASS]`, in [forms_store.py:166](../common/src/python/datastore/forms_store.py#L166)
and [coordinator.py:430-432](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py#L430-L432).
The tag form also supports OR-ing multiple gears, which the metadata-path form did not. But
[delete.py:273](../gear/form_deletion/src/python/form_deletion_app/delete.py#L273) still filters
on the metadata path. `form_deletion` is therefore the only remaining consumer of
`file.info.qc` as a server-side filter, and it will behave differently from the rest of the
pipeline if QC state and `-PASS` tags ever diverge.

**3. `file.info` is pulled wholesale as a single DataView column.**
[scheduling_models.py:136](../common/src/python/curator/scheduling_models.py#L136) requests
`ColumnModel(data_key="file.info", label="file_info")`. This is how `forms`, `raw`, `header`,
`qc`, `derived`, and `resolved` all reach the attribute curator **without any of them appearing
in a column or filter spec**. Any audit that greps only for full paths will conclude these are
unused by DataViews; they are not.

**4. Project metadata is never filtered server-side.** `project.info.studies` and
`project.info.centers` are always fetched whole and filtered in Python — e.g. `NACCGroup.get_center_map()`
fetches the entire center map and then applies `center_filter` in a dict comprehension. The
finder idiom for project info does exist and is used exactly once, on a different key:
[flywheel_proxy.py:372](../common/src/python/flywheel_adaptor/flywheel_proxy.py#L372)
`projects.find(f"info.pipeline_adcid={adcid}")`. In `user-management`, `nacc_group.py:304-307`
does a linear scan across every center's metadata project to find one by pipeline ADCID, where
that query would do the same work server-side.

**5. Two repos are invisible to a path-based audit.** `nacc-file-validator` writes QC results
through `gtk_context.metadata.add_qc_result(...)`, with the `file.info.qc.<gear>` prefix
synthesized inside `flywheel_gear_toolkit` — the string never appears in its source.
`nacc-attribute-deriver` has no Flywheel SDK dependency at all; every path there is a
`SymbolTable` dict key resolved from a namespace prefix constant.

**6. `issue-manager` mimics a DataView client-side.** It builds rows keyed by dotted metadata
paths that look like DataView output, but synthesizes them from `project.files[].info.qc`
already in memory. Its real SDK wrapper, `executeDataView()`
(`issue-manager/src/app/services/fw-client.service.ts:147`), has zero callers.

## Query Sites by Metadata Path

### file.info.forms

Every query site in `flywheel-gear-extensions` routes through one constant and one helper, so
the literal `file.info.forms.json` appears in only one place in the source.

| Repo | Location | Kind | Expression |
|---|---|---|---|
| gear-extensions | [keys.py:81](../common/src/python/keys/keys.py#L81) | path builder | `FORM_METADATA_PATH = "file.info.forms.json"` |
| gear-extensions | [keys.py:86-87](../common/src/python/keys/keys.py#L86-L87) | path builder | `get_column_key()` → `f"{cls.FORM_METADATA_PATH}.{column}"` |

**DataView columns and filters** (`FormsStore`, [forms_store.py](../common/src/python/datastore/forms_store.py)):

| Location | Kind | Expression | Enclosing |
|---|---|---|---|
| [:147](../common/src/python/datastore/forms_store.py#L147) | column | `search_col = f"{FORM_METADATA_PATH}.{search_col}"` | `query_form_data` |
| [:158](../common/src/python/datastore/forms_store.py#L158) | column | `extra_col = f"{FORM_METADATA_PATH}.{extra_lbl}"` | `query_form_data` |
| [:163](../common/src/python/datastore/forms_store.py#L163) | filter | `filters += f",{search_col}{search_op}{search_val}"` | `query_form_data` |
| [:238](../common/src/python/datastore/forms_store.py#L238) | column | `orderby_col = f"{FORM_METADATA_PATH}.{order_by}"` | `query_form_data_with_custom_filters` |
| [:258](../common/src/python/datastore/forms_store.py#L258) | column | `column_lbl = f"{FORM_METADATA_PATH}.{filter_obj.field}"` | `query_form_data_with_custom_filters` |
| [:261](../common/src/python/datastore/forms_store.py#L261) | filter | `filters += f",{column_lbl}{filter_obj.operator}{filter_obj.value}"` | `query_form_data_with_custom_filters` |

**DataView columns and filters** (`form_qc_coordinator`):

| Location | Kind | Expression | Enclosing |
|---|---|---|---|
| [visits.py:80-82](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py#L80-L82) | column | `ptid_key` / `naccid_key` / `date_col_key` via `get_column_key()` | `find_visits_…` |
| [visits.py:93-94](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py#L93-L94) | column | `visitnum_key = get_column_key(VISITNUM)` → `columns.append(visitnum_key)` | `find_visits_…` |
| [visits.py:108](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py#L108) | filter | `filters += f",{date_col_key}{search_op}{cutoff_date}"` | `find_visits_…` |
| [visits.py:161](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py#L161) | filter | `filters = f"acquisition.label={module},{date_col_key}={visitdate}"` | `find_module_visits_with_matching_visitdate` |
| [visits.py:166](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py#L166) | filter | `filters += f",{visitnum_key}={visitnum}"` | `find_module_visits_with_matching_visitdate` |
| [coordinator.py:423](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py#L423) | filter | `filters = f"acquisition.label={supplement_module},{date_col_key}={visitdate}"` | `find_matching_supplement_visit` |
| [coordinator.py:428](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py#L428) | filter | `filters += f",{visitnum_key}={visitnum}"` | `find_matching_supplement_visit` |

One adjacent `file.info.*` DataView column, not among the ten audited paths but worth knowing
about in a migration: [visits.py:97-99](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py#L97-L99)
adds `f"file.info.{MetadataKeys.VALIDATED_TIMESTAMP}"` as an aliased column when
`add_timestamp` is set.

**DataView columns and filters** (`form_deletion`):

| Location | Kind | Expression | Enclosing |
|---|---|---|---|
| [delete.py:222-223](../gear/form_deletion/src/python/form_deletion_app/delete.py#L222-L223) | column | `date_col_key`, `visitnum_key` via `get_column_key()` | `__has_matching_acquisition_files` |
| [delete.py:231](../gear/form_deletion/src/python/form_deletion_app/delete.py#L231) | filter | `filters += f",{date_col_key}={…visitdate}"` | `__has_matching_acquisition_files` |
| [delete.py:235](../gear/form_deletion/src/python/form_deletion_app/delete.py#L235) | filter | `filters += f",{visitnum_key}={…visitnum}"` | `__has_matching_acquisition_files` |
| [delete.py:264](../gear/form_deletion/src/python/form_deletion_app/delete.py#L264) | column | `date_col_key = get_column_key(module_configs.date_field)` | `__has_qc_passed_subsequent_visits` |
| [delete.py:272](../gear/form_deletion/src/python/form_deletion_app/delete.py#L272) | filter | `filters += f",{date_col_key}>{…visitdate}"` | `__has_qc_passed_subsequent_visits` |
| [helpers.py:355-357](../gear/form_deletion/src/python/form_deletion_app/helpers.py#L355-L357) | column | `ptid_key`, `date_col_key`, `visitnum_key` | `__delete_module_acquisitions` |

**Result-key consumers.** These index rows returned by the DataViews above using the same path
prefix. They are not queries, but they break identically if the path changes:
[preprocessor.py](../common/src/python/preprocess/preprocessor.py) (~18 sites),
[legacy_sanity_check main.py:146,218-220](../gear/legacy_sanity_check/src/python/legacy_sanity_check_app/main.py#L146),
[legacy_identifier_transfer main.py:171](../gear/legacy_identifier_transfer/src/python/legacy_identifier_transfer_app/main.py#L171),
[form_qc_checker datastore.py:332](../gear/form_qc_checker/src/python/form_qc_app/datastore.py#L332),
[form_curator.py:244](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py#L244).

**Other repos.** `nacc-attribute-deriver` resolves this path from
`FormNamespace` (`namespace.py:204`, `attribute_prefix = "file.info.forms.json."`) and a prefix
override in `form_meds.py:64`. These are `SymbolTable` keys, not queries.

### file.info.qc

**The only live DataView filter:**

| Repo | Location | Kind | Expression |
|---|---|---|---|
| gear-extensions | [delete.py:273](../gear/form_deletion/src/python/form_deletion_app/delete.py#L273) | **dataview filter** | `filters += f",file.info.qc.{DefaultValues.QC_GEAR}.validation.state=PASS"` |

Executed at [delete.py:275](../gear/form_deletion/src/python/form_deletion_app/delete.py#L275)
via `get_matching_acquisition_files_info(...)`, in `__has_qc_passed_subsequent_visits`.

**Commented-out filters, replaced by tag filters:**

| Location | Replaced by |
|---|---|
| [forms_store.py:166](../common/src/python/datastore/forms_store.py#L166) — `# filters += f",file.info.qc.{qc_gear}.validation.state=PASS"` | [:173](../common/src/python/datastore/forms_store.py#L173) `filters += f",file.tags=\|[{','.join(tags)}]"` |
| [coordinator.py:430-432](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py#L430-L432) | [:438](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py#L438) `filters += f",file.tags=\|[{','.join(tags)}]"` |

In both cases the tag list is built as `f"{gear}-PASS"` per gear, enabling an OR across multiple
QC gears — something the single-valued metadata filter could not express.

**issue-manager — synthetic DataView column keys (no server-side query):**

| Location | Kind | Expression |
|---|---|---|
| `src/app/services/dataview.service.ts:83` | path builder | `return "file.info.qc."+gearName+".validation.data"` (`dataLocation`) |
| `src/app/services/dataview.service.ts:87` | path builder | `` `file.info.qc.${gearName}.validation.cleared` `` (`clearedLocation`) |
| `src/app/services/dataview.service.ts:107` | column key (write) | `` [`file.info.qc.${gearName}.validation.data`]: qcData `` |
| `src/app/services/dataview.service.ts:108` | column key (write) | `` [`file.info.qc.${gearName}.validation.cleared`]: qcClear `` |
| `src/app/services/dataview.service.ts:43,45` | column key (read) | `dataviewRow[this.dataLocation(gearName)]` |

`makeProjectDataview()` (line 90) constructs rows in memory that mimic a DataView response,
keyed by dotted paths alongside `'project.id'` and `'file.file_id'`. The only filtering is
client-side: `if (Object.keys(qc).length === 0) { continue }` at line 98. There is no
`DataViewBuilder`, `columns=`, or `filter=` anywhere in the repo. The real SDK entry point,
`fw-client.service.ts:147` `executeDataView()`, is unreferenced.

**SymbolTable lookups in the attribute curator.** Not server-side filters — these key into the
whole-`file.info` DataView column described in Key Finding 3, in `FormCurator.check_qc`
([form_curator.py:158-178](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py#L158-L178)):
`file.info.qc.nacc-file-validator.validation.state`, `file.info.qc.form-qc-checker.validation.state`,
`file.info.qc.file-validator.validation.state`, `file.info.qc.form-importer.metadata-extraction.state`.

**No query sites** in `nacc-attribute-deriver`, `user-management` (one prose mention in an
archived design doc, `docs/archive/portal-access-model/PORTAL_DASHBOARD_ENDPOINTS.md:766`),
`data-platform-admin-tasks`, or `nacc-file-validator`.

### file.info.resolved

No query sites in any repo. Written and cleared only:

- [form_curator.py:143](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py#L143) — `table.pop(f"file.info.{field}")` for `derived`/`resolved`
- [form_curator.py:243](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py#L243) — `__set_working_metadata(table, "file.info.resolved", …)`
- [form_curator.py:594-597](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py#L594-L597) — `update_info` write
- [curation_keys.py:37-52](../gear/attribute_curator/src/python/attribute_curator_app/curation_keys.py#L37-L52) — `RESOLVED_SCOPES`, gating the write
- `nacc-attribute-deriver` config CSVs: 1351 rows in `file_missingness.csv` and 9 in
  `test_missingness.csv` target `file.info.resolved.*` as write destinations

### file.info.raw

No query sites. Reached via the whole-`file.info` DataView column and read in Python:

- [scheduling_models.py:210](../common/src/python/curator/scheduling_models.py#L210) — `raw_data = self.file_info.get("raw", {})` in `FileModel.__determine_file_date`
- `nacc-attribute-deriver` `namespace.py:222` — `RawNamespace`, `attribute_prefix = "file.info.raw."`

### file.info.header

No query sites. Direct reads only:

- [scheduling_models.py:216](../common/src/python/curator/scheduling_models.py#L216) — `self.file_info.get("header", {}).get("dicom", {})`
- [image_submission_form.py:177,182,186,221-222,233-234](../common/src/python/redcap_imaging_forms/image_submission_form.py#L177) — `file.info["header"]["dicom"][…]` after `.reload()`
- `nacc-attribute-deriver` `image_namespace.py:17` — `MixedProtocolNamespace`, prefix `"file.info.header.dicom."`

### file.info.derived

No query sites. Written by the curator alongside `resolved` (see
[file.info.resolved](#fileinforesolved)). In `nacc-attribute-deriver`, `namespace.py:241`
(`DerivedNamespace`, prefix `"file.info.derived."`) plus 149 write rows in
`curation_rules.csv` and 2 in `file_missingness.csv` (`file.info.derived.naccvnum`).

### file.info.config

**Not present in any of the six repositories**, in any role. The single grep hit in this repo,
[coordinator.py:830](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py#L830)
`config=self.__qc_gear_info.configs.model_dump()`, is a false positive on the substring
`info.config`.

### project.info.studies

No query sites in any repo. Fetched whole via `get_info()` and filtered in Python:

| Repo | Location | Expression |
|---|---|---|
| gear-extensions | [center_group.py:330](../common/src/python/centers/center_group.py#L330) | `project_info.studies.get(redcap_project.study_id, None)` |
| gear-extensions | [center_group.py:375-379](../common/src/python/centers/center_group.py#L375-L379) | `info = metadata_project.get_info()` → `if "studies" not in info:` |
| gear-extensions | [redcap_project_creation run.py:169-170](../gear/redcap_project_creation/src/python/redcap_project_creation_app/run.py#L169-L170) | `if not info or "studies" not in info:` |
| user-management | `reference-code/common/src/python/centers/center_group.py:326,371,375` | same pattern, then `CenterMetadata.model_validate(info)` |
| user-management | `common/src/python/center/flywheel_center_adapter.py:127-136` | `if not info or "studies" not in info:` |
| admin-tasks | `scripts/clear_center_studies/…/run.py:84-94` | `info_object.pop("studies")` → `project.replace_info(info_object)` |

Note that `clear_center_studies` takes its center list from `data/studies/<id>/study.yaml`, not
from Flywheel, so no query is needed there.

### project.info.centers

No query sites in any repo. Fetched whole, then filtered client-side:

| Repo | Location | Expression |
|---|---|---|
| gear-extensions | [nacc_group.py:103-116](../common/src/python/centers/nacc_group.py#L103-L116) | `if "centers" not in info:` → `info["centers"] = {…}` |
| gear-extensions | [redcap_project_creation main.py:93](../gear/redcap_project_creation/src/python/redcap_project_creation_app/main.py#L93) | `for center in study_info.centers:` |
| user-management | `reference-code/common/src/python/centers/nacc_group.py:103-116` | `get_center_map(center_filter)` — filter applied in a dict comprehension after the full fetch |
| user-management | `common/src/python/center/flywheel_center_adapter.py:92-98` | `centers = info.get("centers", {})`, then comprehension |

Documented at [docs/push_template/index.md:21](push_template/index.md), but no code queries it.
`data-platform-admin-tasks` does not reference it at all — its center data is file-backed
(`centers.yaml`, `data/studies/{study_id}/centers.csv`).

### subject.info.derived

No query sites in any repo.

- [form_curator.py:118-124](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py#L118-L124) — `parent_location = "subject.info.derived.cross-sectional."`, used as a string prefix to strip from deriver rule attribute names. Not a Flywheel path expression.
- [curator.py:133](../common/src/python/curator/curator.py#L133) — `table["subject.info"] = subject_table.to_dict()`, a local table key
- `nacc-attribute-deriver` `namespace.py:277` — `SubjectDerivedNamespace`, prefix `"subject.info.derived."`; 211 write rows in `curation_rules.csv` and 30 in `subject_missingness.csv` (all `subject.info.derived.cross-sectional.*`)

**Closest real query elsewhere:** `data-platform-admin-tasks`
`scripts/create_center_dataviews/…/run.py:30-35` defines a DataView with five columns on the
sibling path `subject.info.enrollment.*` (`adcid`, `ptid`, `naccid`, `guid`, `update_date`) and
**no filter expression at all**. It is the only DataView outside `flywheel-gear-extensions` with
a concrete column list fixed in source, and it demonstrates that `subject.info.*` paths are
viable as DataView columns. The same five columns appear in the pre-migration notebook
`notebooks/migrated/center-dataviews.ipynb:50-54`.

## Path Builders and Constants

The indirection layer. Changing a metadata path means changing these, not the call sites.

| Repo | Location | Constant / helper | Value |
|---|---|---|---|
| gear-extensions | [keys.py:81](../common/src/python/keys/keys.py#L81) | `MetadataKeys.FORM_METADATA_PATH` | `file.info.forms.json` |
| gear-extensions | [keys.py:86-87](../common/src/python/keys/keys.py#L86-L87) | `MetadataKeys.get_column_key()` | `<FORM_METADATA_PATH>.<column>` |
| issue-manager | `dataview.service.ts:83` | `dataLocation(gearName)` | `file.info.qc.<gear>.validation.data` |
| issue-manager | `dataview.service.ts:87` | `clearedLocation(gearName)` | `file.info.qc.<gear>.validation.cleared` |
| deriver | `namespace.py:204` | `FormNamespace` | `file.info.forms.json.` |
| deriver | `namespace.py:222` | `RawNamespace` | `file.info.raw.` |
| deriver | `namespace.py:241` | `DerivedNamespace` | `file.info.derived.` |
| deriver | `namespace.py:258` | `SubjectInfoNamespace` | `subject.info.` |
| deriver | `namespace.py:277` | `SubjectDerivedNamespace` | `subject.info.derived.` |
| deriver | `namespace.py:446` | `SubjectWorkingNamespace` | `subject.info.working.` |
| deriver | `image_namespace.py:17` | `MixedProtocolNamespace` | `file.info.header.dicom.` |
| deriver | `keyed_namespace.py:24` | `PreviousRecordNamespace` | `_prev_record.info.` |
| deriver | `keyed_namespace.py:151` | `ProvenanceNamespace` | `file.info.provenance.` |
| deriver | `form_meds.py:64` | `MEDSFormAttributeCollection` | `file.info.forms.json` (no trailing dot) |

One path builder uses an incompatible separator and should not be treated as DataView-ready:
`user-management` `reference-code/common/src/python/flywheel_adaptor/flywheel_proxy.py:1651`
`ProjectAdaptor.get_custom_project_info(key_path)` splits on **colons** (`level1:level2:…`) and
walks an already-fetched dict client-side. It has no call sites in that repo.

## DataView Inventory

Every DataView construction site across the six repos, and what its columns and filters
actually reference.

| Repo | Location | Container | Columns | Filter |
|---|---|---|---|---|
| gear-extensions | [flywheel_proxy.py:777-789](../common/src/python/flywheel_adaptor/flywheel_proxy.py#L777-L789) | `acquisition` | caller-supplied | caller-supplied — **the main chokepoint** |
| gear-extensions | [dataview.py:20-38](../common/src/python/data/dataview.py#L20-L38) | caller-supplied | caller-supplied | `filter=filter_str`, caller-supplied |
| gear-extensions | [scheduling_models.py:127-147](../common/src/python/curator/scheduling_models.py#L127-L147) | `acquisition` | `file.name`, `file.file_id`, `file.tags`, **`file.info`**, `file.modified`, `file.parents.session` | none — only `builder.file_filter()` on filename regex |
| gear-extensions | [form_scheduler_queue.py:363-378](../gear/form_scheduler/src/python/form_scheduler_app/form_scheduler_queue.py#L363-L378) | `acquisition` | `file.name`, `file.file_id`, `acquisition.label` | `acquisition.label=\|[…],file.tags=<tag>` |
| gear-extensions | [delete.py:299-315](../gear/form_deletion/src/python/form_deletion_app/delete.py#L299-L315) | `acquisition` | `file.name`, `file.file_id` | `acquisition.label=\|[…]` |
| gear-extensions | [template_project.py:171-196](../common/src/python/projects/template_project.py#L171-L196) | — | copied verbatim from template | filter text lives in Flywheel, not this repo |
| admin-tasks | `create_center_dataviews/…/run.py:25-41` | default | `subject.info.enrollment.{adcid,ptid,naccid,guid,update_date}` | none |
| admin-tasks | `common/src/python/common/dataview.py:13-38` | caller-supplied | caller-supplied | `filter_str` — **`None` at every call site** |
| user-management | `reference-code/…/flywheel_proxy.py:773-782` | `acquisition` | caller-supplied | caller-supplied — **no call sites in that repo** |
| issue-manager | `fw-client.service.ts:147-151` | — | — | `executeDataView()` — **zero callers** |
| deriver | — | — | — | no DataView code |
| file-validator | — | — | — | no DataView code |

The three DataViews with concrete column lists (`scheduling_models.py`,
`form_scheduler_queue.py`, `create_center_dataviews`) plus the `template_project` copies are the
only places where a column spec is fixed in source. Everything else is parameterized.

## Finder Query Inventory

No `find`/`search` call in any repo queries one of the ten target paths. The full set of
`info.*` finder queries across all six repos is a single expression, on a non-target key:

| Repo | Location | Query |
|---|---|---|
| gear-extensions | [flywheel_proxy.py:372](../common/src/python/flywheel_adaptor/flywheel_proxy.py#L372) | `projects.find(f"info.pipeline_adcid={adcid}")` |
| user-management | `reference-code/…/flywheel_proxy.py:372` | same expression (vendored copy) |

All other finder queries use `label`, `_id`, `parents.*`, `file.tags`, `name=~`, `modality`, or
`parent_ref.type`. Two that are QC-adjacent but filename-based, not metadata-based:

- [event_processor.py:153](../common/src/python/event_capture/event_processor.py#L153) — `get_matching_files("parent_ref.type=project,name=~.+qc-status.log")`
- `data-platform-admin-tasks` `scripts/experiments/…/experiment.py:48-55` — `parents.project=…`, `parent_ref.type=project`, `name=~.+qc-status.log`

## Appendix: Direct Reads and Writes

Summarized rather than enumerated. These break on a metadata **shape** change but are invisible
to a query audit.

### flywheel-gear-extensions

`file.info.qc` appears in ~40 source locations, nearly all docstrings describing the convention
(`qc_reader.py`, `error_logger.py`, `error_models.py`, `uploader.py`, `qc_report.py`,
`pipeline_event_logger/main.py`, `form_qc_checker/processor.py`, `dicom_qc_checker/main.py`,
and others). Live accesses go through pydantic models — e.g.
[error_logger.py:406-407](../common/src/python/error_logging/error_logger.py#L406-L407)
`del qc_info.qc[gear_name]`. `file.info.raw` / `header` / `forms` are read off the whole-`info`
DataView column in [scheduling_models.py:204-216](../common/src/python/curator/scheduling_models.py#L204-L216).
`project.info.studies` / `centers` are read via `get_info()` in `center_group.py` and
`nacc_group.py`. Note [data_request.py:196-202](../common/src/python/data_requests/data_request.py#L196-L202)
builds a `file.info.<path>` string **for an error message only**; the actual lookup is
`SymbolTable(file.info)[path]` after `file.reload()`.

### issue-manager

All on `info.qc`. Reads in `dataview.service.ts:95,102-103`, `fw-client.service.ts:111-114`
(`aggregateQcGearNames` discovers gear names by iterating `file.info['qc']` keys),
`clear-button.service.ts:132`. Writes in `clear-button.service.ts:163-164`
(`{set: {qc: qcInfo}}` — replaces the whole `info.qc` subtree) and
`finalize-alerts.service.ts:155,164,201-206` (sets `validation.state = 'PASS'`), plus
`file.info.validated-timestamp` at `:213` and `subject.info.<module>.failed` at `:219-224`
(note: `subject.info`, not `subject.info.derived`). Separately,
`project.info.issue_manager.table_settings` is read at `app.component.ts:41` and written at
`table-settings.service.ts:130-136`.

### nacc-attribute-deriver

Every path is a `SymbolTable` dict key; there is no Flywheel SDK dependency. Hard-coded full
paths in source are few: `attribute_deriver.py:256-257`
(`file.info.forms.json.formver`, `.packet`), `form_np.py:30` and `missingness_np.py:41`
(`file.info.forms.json.visitdate`). The bulk of usage is data-driven via the config CSVs'
`location` column — `file_missingness.csv` (1351 → `file.info.resolved.*`, 2 →
`file.info.derived.naccvnum`), `curation_rules.csv` (211 → `subject.info.derived.*`, 149 →
`file.info.derived.*`, 69 → `subject.info.working.*`, plus smaller counts under
`subject.info.{imaging,cognitive,demographics,longitudinal-data,study-parameters}`),
`subject_missingness.csv` (30 → `subject.info.derived.cross-sectional.*`), `test_missingness.csv`
(9 → `file.info.resolved.*`). Tests contain ~800 further `table["<path>"] = value` writes, not
enumerated.

### user-management

`project.info.studies` and `project.info.centers` reads as listed in their sections above.
Generic accessors that could reach any path without a literal: `ProjectAdaptor.get_info()` /
`update_info()` (`flywheel_proxy.py:1633-1649`), `subject_adaptor.py:36,107,131,146`
(`self.info.get(module)`), `gear_execution.py:351` (`file.info.get("uploader")`). Direct reads
of `project.info.pipeline_adcid` / `adcid` at `flywheel_proxy.py:1222,1226`; writes at
`study_mapping.py:340,375`.

### data-platform-admin-tasks

`project.info.studies` read/pop/replace in `clear_center_studies/…/run.py:84-94`. A generic
write path exists at `set_project_info/…/run.py:98` (`project.update_info({args.key: data})`)
where the key is CLI-supplied, so `studies` or `centers` can be written without appearing as a
literal. Center data is otherwise file-backed.

### nacc-file-validator

No target path appears in the source. QC results are written at `errors.py:229-237` via
`gtk_context.metadata.add_qc_result(input_file.name, "validation", state=state, **meta_dict)`;
the `file.info.qc.<gear>` prefix is synthesized inside `flywheel_gear_toolkit`. `loader.py:20`
includes `"info"` in `PARENT_INCLUDE`, the whitelist of container fields hydrated for
validation — it selects the whole `info` blob, never a sub-path.

## Files Referenced

Files that matter for a metadata path migration, in rough order of blast radius.

| File | Role |
|---|---|
| [common/src/python/keys/keys.py](../common/src/python/keys/keys.py) | `FORM_METADATA_PATH` + `get_column_key()` — single source for every `file.info.forms.json` query |
| [common/src/python/datastore/forms_store.py](../common/src/python/datastore/forms_store.py) | Main DataView query builder; commented-out QC filter |
| [common/src/python/flywheel_adaptor/flywheel_proxy.py](../common/src/python/flywheel_adaptor/flywheel_proxy.py) | `get_matching_acquisition_files_info`, `get_files`, the one `info.*` finder query |
| [common/src/python/curator/scheduling_models.py](../common/src/python/curator/scheduling_models.py) | Whole-`file.info` DataView column; `raw`/`header` reads |
| [gear/form_deletion/.../delete.py](../gear/form_deletion/src/python/form_deletion_app/delete.py) | **The only live `file.info.qc` DataView filter** |
| [gear/form_qc_coordinator/.../coordinator.py](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/coordinator.py) | Commented-out QC filter; supplement-visit DataView |
| [gear/form_qc_coordinator/.../visits.py](../gear/form_qc_coordinator/src/python/form_qc_coordinator_app/visits.py) | Visit-lookup DataView columns and filters |
| [gear/attribute_curator/.../form_curator.py](../gear/attribute_curator/src/python/attribute_curator_app/form_curator.py) | QC state reads; `derived`/`resolved` writes; `subject.info.derived` prefix |
| [common/src/python/centers/nacc_group.py](../common/src/python/centers/nacc_group.py) | `project.info.centers` fetch + client-side filter |
| [common/src/python/centers/center_group.py](../common/src/python/centers/center_group.py) | `project.info.studies` fetch |
| [common/src/python/data/dataview.py](../common/src/python/data/dataview.py) | Generic `ViewBuilder` factory |
| `issue-manager/src/app/services/dataview.service.ts` | `file.info.qc` path builders and synthetic column keys |
| `issue-manager/src/app/services/fw-client.service.ts` | Unused `executeDataView()` SDK hook |
| `nacc-attribute-deriver/…/attributes/namespace/namespace.py` | Authoritative namespace prefixes for five paths |
| `nacc-attribute-deriver/nacc_attribute_deriver/config/*.csv` | Data-driven write destinations |
| `nacc-file-validator/fw_gear_file_validator/errors.py` | Toolkit-mediated `file.info.qc` write |
| `data-platform-admin-tasks/scripts/create_center_dataviews/…/run.py` | The one `subject.info.*` DataView |
