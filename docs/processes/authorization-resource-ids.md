# Authorization Resource IDs and Labels

Resources in the Authorization API are identified structurally: a resource
**type**, a resource **label**, and explicit parent references (`study`,
`center`, `community`). This document defines the **resource label**, so the
definition can be referenced rather than re-derived.

The API also exposes a flat, opaque identifier (`resource.flat_id`) that encodes
the same information as a single string. Clients **do not construct or parse**
the flat ID — the Authorization API owns it. See the section below.

## The flat ID is server-owned (do not construct)

Historically clients built a flat resource ID by concatenating the label with a
center prefix and study suffix. **That is no longer done.** Under the structured
`resource` contract (Increment 5 of the Authorization API client migration
notes), identity travels in the structured `resource` field — the label plus
the parent references — and the flat form is:

- **On requests:** never sent. Send `type`, `label`, and the parent fields.
- **On responses:** returned as the read-only `resource.flat_id` handle. Treat
  it as an opaque value you may echo back verbatim (for example, as a
  `{resourceId}` path segment on a GET read), but never build or split it.

For reference, the server's flat form follows the ADR-016 shape
`{center}_{label}-{study_id}` (both scoping parts optional; `study_id` explicit
when present; the `_` separator is safe because center names never contain
underscores). This is documented only so the handle is recognizable — clients
must not reproduce this assembly.

## Resource label

A **resource label** is the resource-identifying core of a resource — it says
*what* the resource is, independent of which center or study it belongs to. It
is the value carried in the structured `resource.label` field, and (in the
server-owned flat ID) the part left after stripping the optional `{center}_`
prefix and `-{study_id}` suffix.

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

Two producers build labels. Each supplies the label (plus the resource type and
parent references) to the structured `resource` field of an API request; neither
assembles a flat ID.

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
