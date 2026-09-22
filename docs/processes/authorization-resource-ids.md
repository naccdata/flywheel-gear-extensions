# Authorization Resource IDs and Labels

Resources in the Authorization API are identified by a resource ID following
the ADR-016 format. This document defines the parts of that ID, and in
particular the **resource label**, so the definition can be referenced rather
than re-derived.

## Resource ID format

```
{center}_{label}-{study_id}
```

Both scoping parts are optional:

- Center-scoped: `{center}_{label}-{study_id}`
- Non-center: `{label}-{study_id}`
- Without study: `{center}_{label}` or `{label}`

The `_` separator before the label is safe because center names never contain
underscores. The `study_id`, when present, is always explicit.

The ID is assembled by `build_resource_id` in
`common/src/python/authorization_sync/resource_ids.py`, which only adds the
`{center}_` prefix and `-{study_id}` suffix. The caller supplies the label.

## Resource label

A **resource label** is the resource-identifying core of a resource ID — the
part left after stripping the optional `{center}_` prefix and `-{study_id}`
suffix. It says *what* the resource is, independent of which center or study it
belongs to.

A label has the form:

```
{kind}-{name}
```

- **kind** — the resource category. One of:
  `ingest`, `sandbox`, `retrospective`, `distribution`, `accepted`,
  `dashboard`, `page`.
  The pipeline kinds (`ingest`, `sandbox`, `retrospective`, `distribution`,
  `accepted`) correspond to `PipelineStageType` in `common/src/python/keys/types.py`.
- **name** — the specific instance within that kind. For pipeline kinds it is a
  datatype (one of `DatatypeNameType` in `keys/types.py`, e.g. `form`,
  `enrollment`, `scan-analysis`). For `dashboard` and `page` it is the
  dashboard or page name.

### Exceptions to the form

- `accepted` stands alone with no `-{name}` part; its label is just `accepted`.
- A `name` may itself contain hyphens (e.g. `scan-analysis`, giving the label
  `ingest-scan-analysis`). Split a label into `kind` and `name` at the **first**
  `-`, not on every `-`.

## Where labels are built

Two producers build labels and then share `build_resource_id` for formatting:

- **Grant path (user_management gear)** —
  `common/src/python/authorization_sync/translator.py` builds labels via
  `build_label_for_resource_prefix`, which maps the gear's internal resource
  prefix to the label kind: `datatype` → `ingest`, `dashboard` → `dashboard`,
  `page` → `page`. This path only ever produces `ingest`, `dashboard`, and
  `page` labels.
- **Seed path (project_management gear)** —
  `common/src/python/projects/study_mapping.py` builds labels inline for the
  full set of kinds (including `sandbox`, `retrospective`, `distribution`, and
  `accepted`) and lowercases datatype names.

Grant coverage is therefore a subset of seeded resources: the seeder creates
pipeline resources (`sandbox`, `retrospective`, `distribution`, `accepted`)
that the grant path does not target.
