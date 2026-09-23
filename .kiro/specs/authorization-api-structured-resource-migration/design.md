# Design Document

## Overview

The NACC Authorization API moved resource identity into a single structured
`resource` field (Increment 5 of the client migration notes). This is a
breaking change: write requests are rejected with HTTP 400 if they carry the
legacy top-level `type`/`resourceId` fields, and responses now carry identity
only in the structured `resource` field, exposing the flat identifier solely as
the read-only `resource.flat_id` handle.

This design migrates the client library (`common/src/python/authorization/`) and
the auth sync orchestration (`common/src/python/authorization_sync/`) to that
contract. It is a **targeted migration, not a rewrite**: the module layout,
model classes, sync flow, label producers, scope-aware revocation, retry
behavior, batch chunking, and event reporting are all preserved. Only what the
structured-`resource` contract forces changes.

### The resource-identity principle (read this first)

Every decision in this document follows from one principle that prior work
repeatedly got wrong:

> **Resource identity is structured, not a string.** A resource is identified by
> its **type**, its **label**, and its explicit **parent fields** (`center`,
> `study`, `community`). The flat identifier (`flat_id`) is a server-owned,
> opaque handle — the client never builds it, never parses it, and never uses it
> as a matching key.

Concretely:

- **Requests** send `type`, `label`, and the applicable parent fields inside a
  `resource` object. They never send `flat_id`, a top-level `type`, or a
  top-level `resourceId`.
- **Responses** carry identity in `resource` (type + label + parents) and expose
  `flat_id` as a read-only handle. The client reads identity from the structured
  fields; it may echo `flat_id` verbatim as a `{resourceId}` path segment on GET
  reads but never decomposes it.
- **Diffing** desired grants against current grants keys on the **Structured
  Identity Tuple** `(type, relation, label, center, study, community)` for both
  sides. `flat_id` is never part of the key, so matching no longer depends on the
  client reproducing the server's flat string byte-for-byte.
- **Missing identity** (a response entry with `resource == None`, i.e. a catalog
  gap) is excluded from the diff entirely and is never revoked.

## Architecture

The migration touches four layers. Identity flows as structured fields from the
translator through the diff into the request body; `flat_id` only ever flows
back on the response path and is treated as opaque.

```mermaid
flowchart TD
    subgraph Grant path (user_management gear)
        A[Authorizations / StudyAuthorizations] --> T[translate&#40;&#41;]
        LP[build_label_for_resource_prefix<br/>label producer, KEEP] --> T
        T --> DG[DesiredGrant<br/>type + relation + label<br/>+ center/study/community]
    end

    subgraph Diff (sync_service)
        DG -->|desired set| DIFF[Structured Identity Tuple diff]
        CUR[current grants] -->|in-scope subset| DIFF
        DIFF --> ADD[grants_to_add]
        DIFF --> REV[grants_to_revoke]
    end

    subgraph Client (authorization/client.py)
        ADD --> OP[BatchOperation / GrantRequest / RevokeRequest]
        REV --> OP
        OP --> RO[resource object<br/>type + label + parents<br/>NO flat_id]
        RO -->|POST/DELETE| API[(Authorization API)]
    end

    API -.->|response: resource incl. flat_id| PARSE[parse structured resource]
    PARSE -.->|resource.center / community / label| CUR
    PARSE -.->|flat_id opaque, echo only| GETPATH[GET reads path segment]

    style RO fill:#e8f5e9
    style DIFF fill:#e3f2fd
    style PARSE fill:#fff3e0
```

Note the direction of `flat_id`: it appears only on the dotted response edges. No
solid (request) edge carries it, and no edge feeds it into the diff key.

### What changes vs. what is held constant

Changed (forced by the contract):

- `ResourceObject`: `id` → `label` (required); `flat_id` becomes optional,
  read-only, excluded from request serialization; parent fields validated per
  type.
- Write-request models (`GrantRequest`, `RevokeRequest`, `BatchOperationModel`,
  `PermissionCheckRequest`): stop emitting top-level `type`/`resourceId`; embed a
  structured `resource`.
- `DesiredGrant`: carries `resource_label` + `center`/`study`/`community` instead
  of a pre-built flat `resource_id`.
- `translate()`: populates `DesiredGrant` structured fields; no longer calls
  `build_resource_id` for the grant path.
- `to_grants` / `_grants_in_scope`: build `DesiredGrant` from `entry.resource`
  structured fields instead of `entry.resource_id`.
- `client.py`: request construction, response-identity parsing, and idempotent
  409/404 result construction switch to the structured `resource`.

Held constant (Requirement 9, Requirement 10):

- Module layout under `authorization/` and `authorization_sync/`.
- `ACTIVITY_RELATION_MAP` (keys, values, associations), `validate_activity_relation_map`, `check_assignable`.
- Per-type permissions query loop (ADR-015), `_SYNC_RESOURCE_TYPES` derivation.
- Batch chunking (`_BATCH_CHUNK_SIZE = 100`, order preserved), `retry_on_503`
  (same max retries / backoff), `_IDEMPOTENT_ERROR_CODES = {conflict, not_found}`.
- `sync_user`/`sync_users` scoping semantics and event-collector partial-failure
  reporting.
- The `build_resource_id` seed-path label producer (kept — see Migration plan).

## Resource identity model

This section is the normative definition of identity for the migration.

### Structured Identity

The **Structured Identity** of a resource is:

| Component | Field | Notes |
|-----------|-------|-------|
| Resource Type | `resource.type` | e.g. `data_pipeline`, `dashboard`, `page`, or an organization type |
| Resource Label | `resource.label` | the resource-identifying core, form `{kind}-{name}` |
| Parent: study | `resource.study` | optional, per type |
| Parent: center | `resource.center` | optional, per type |
| Parent: community | `resource.community` | optional, per type |

The **Resource Label** has the form `{kind}-{name}` where `kind` is one of
`ingest`, `sandbox`, `retrospective`, `distribution`, `accepted`, `dashboard`,
`page`. Two rules matter for correctness:

- `accepted` stands alone with no `-{name}` part; its label is just `accepted`.
- A `name` may itself contain hyphens (e.g. `scan-analysis` → label
  `ingest-scan-analysis`). **Split a label into `kind` and `name` at the first
  `-` only**, never on every `-`.

Labels are produced by the two existing **Label Producers** and never
reconstructed elsewhere:

- Grant path: `build_label_for_resource_prefix` in `translator`/`resource_ids.py`
  (`datatype`→`ingest-{name}`, `dashboard`→`dashboard-{name}`, `page`→`page-{name}`).
- Seed path: the inline builder in `projects/study_mapping.py`.

### The Structured Identity Tuple (the diff key)

The **Structured Identity Tuple** is the sole matching key for a grant on both
the desired and current sides of the diff:

```
(resource_type, relation, resource_label, center, study, community)
```

Comparison rules (Requirement 5.3):

- Six components, compared pairwise.
- Each string component uses exact, **case-sensitive** equality.
- An absent (`None`) component equals only another absent component (`None`).
  `None` never equals `""`.
- `flat_id` is **not** a component and never participates in the key
  (Requirement 5.2).

### flat_id is opaque

`flat_id` is the server-owned flat identifier returned on responses. The client:

- never sends it on a request (excluded from request serialization),
- never constructs it,
- never parses/splits/truncates it to derive type, label, or parents,
- may echo it verbatim, byte-for-byte, as a `{resourceId}` path segment on a GET
  read (Requirement 4.5, 4.6).

For reference only, the server's flat form follows ADR-016
`{center}_{label}-{study_id}`; this is documented so the handle is recognizable,
not so the client can reproduce it.

### Conditional parent fields per type (Requirement 2.6–2.9)

Which parent fields a `resource` may carry depends on its type. The
`ResourceObject` validator enforces exactly these combinations:

| Resource Type | Allowed parent-field combinations |
|---------------|-----------------------------------|
| organization type | none of `study`/`center`/`community` |
| `data_pipeline` | (`study` + `center`) or (`study` alone) |
| `dashboard` | (`study` + `center`) or (`study` alone) or (`community` alone) |
| `page` | (`study` + `center`) or (`study` alone) or (`center` alone) or (`community` alone) |

Any other combination is rejected with a validation error naming the offending
type. Organization types are recognized by an explicit set of organization type
names (see Data Models); every other type is treated as a resource type and must
match one of the resource combinations. A type not in the per-type table and not
an organization type carries no parent-field combination constraint beyond the
general "label required" rule, so unknown/forward-compatible types are not
rejected solely for their parents.

## Components and Interfaces

### `authorization/models.py`

#### `ResourceObject` (corrected in place — Requirement 2, 10.1)

A single model used for both request serialization and response parsing.

```python
class ResourceObject(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str
    label: str = Field(min_length=1)          # was: id (removed)
    flat_id: str | None = Field(default=None, alias="flatId")  # read-only handle
    name: str | None = None
    study: str | None = None
    center: str | None = None
    community: str | None = None

    @model_validator(mode="after")
    def check_parent_fields(self) -> "ResourceObject": ...

    def request_dump(self) -> dict[str, Any]:
        """Serialize for a request body, excluding flat_id."""
        return self.model_dump(by_alias=True, exclude_none=True,
                               exclude={"flat_id"})
```

Field-level changes:

- **`label` required** (Requirement 2.1): `min_length=1` so a missing or empty
  label is a validation error. Replaces the removed `id`.
- **`id` removed** (Requirement 2.2): `extra="ignore"` means an incoming `id`
  field on a parsed response is dropped and never serialized back.
- **`flat_id` read-only** (Requirement 2.3, 2.4): defaults to absent, populated
  only when parsing a response, and excluded from request output. Serialization
  for requests goes through `request_dump` (or an equivalent `model_dump(...,
  exclude={"flat_id"})`), so no request body ever contains `flat_id`.
- **Parent fields** (Requirement 2.5): `study`, `center`, `community` are all
  optional; `type` and `name` remain.
- **`check_parent_fields`** enforces the per-type combination table above and
  raises a `ValueError` naming the type on violation.

Request models embed a `ResourceObject` and expose helpers so `client.py` builds
identity from the tuple, not from a flat string.

#### Write-request models (Requirement 1)

The root cause of Requirement 1's blocking bug is `_ResourceObjectValidatorMixin`,
which serializes top-level `type` + `resourceId`. The migration replaces that
mixin's role for write requests with an embedded structured `resource`.

```python
class GrantRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(alias="userId")
    relation: str
    resource: ResourceObject

    def request_body(self) -> bytes:
        payload = {"userId": self.user_id, "relation": self.relation,
                   "resource": self.resource.request_dump()}
        return json.dumps(payload).encode()
```

- `RevokeRequest` and `PermissionCheckRequest` mirror `GrantRequest`.
- `BatchOperationModel` gains `resource: ResourceObject` and drops the top-level
  `type`/`resourceId`; `action`/`user_id`/`relation` are unchanged.
- The legacy top-level `type`/`resourceId` fields are removed from these four
  models so they cannot be emitted (Requirement 1.2).
- Serialization excludes `flat_id` (Requirement 1.3) and requires a non-empty
  `label` (Requirement 1.4, enforced by `ResourceObject`).
- If a caller supplies no type, an empty label, or a parent-field combination
  invalid for the type, construction raises before any HTTP call (Requirement
  1.7, 2.6–2.9).
- `_ResourceObjectValidatorMixin` is retained only if a non-write model still
  needs the combined-length check; otherwise it is removed. Its length rule does
  not apply to the structured `resource` (which sends discrete fields, not a
  concatenated `type:resourceId`).

#### Response models (Requirement 4)

`GrantResult`, `RevokeResult`, `PermissionEntry`, `ResourceParents`, and
`ResourceListItem` already carry `resource: ResourceObject | None`. The change is
to **read identity from `resource`** and stop reading the top-level
`resource_id`/`resourceId`:

- The top-level `resource_id` alias fields are removed from these response models
  (or retained only as ignored input), so parsing cannot fall back to them
  (Requirement 4.2, 4.4).
- When `resource` is `None` (catalog gap), the entry has no Structured Identity;
  callers treat it accordingly rather than reconstructing a partial identity
  (Requirement 4.3).

`UserPermissions.to_grants` changes its factory contract to pass structured
fields instead of a flat `resource_id`:

```python
def to_grants(self, factory: Callable[..., Any]) -> set:
    grants: set = set()
    for resource_type, entries in self.permissions.items():
        for entry in entries:
            if entry.resource is None:
                # catalog gap: no structured identity -> skip (Req 4.3, 6)
                log.warning("Permissions entry for type %s has no resource; "
                            "skipping (catalog gap)", resource_type)
                continue
            grants.add(factory(self.user_id, entry.resource, entry.relation))
    return grants
```

### `authorization_sync/models.py`

#### `DesiredGrant` (Requirement 3.1, 3.2, 10.3)

Remains a frozen dataclass (hashable, usable in sets), but carries the Structured
Identity rather than a flat `resource_id`:

```python
@dataclass(frozen=True)
class DesiredGrant:
    user_id: str
    resource_type: str
    relation: str
    resource_label: str
    center: str | None = None
    study: str | None = None
    community: str | None = None

    def __post_init__(self) -> None:
        if not self.resource_type or not self.resource_label:
            raise ValueError(
                "DesiredGrant requires resource_type and resource_label"
            )

    def identity(self) -> tuple[str, str, str, str | None, str | None, str | None]:
        """The Structured Identity Tuple used as the diff key."""
        return (self.resource_type, self.relation, self.resource_label,
                self.center, self.study, self.community)

    def to_resource(self) -> ResourceObject:
        return ResourceObject(type=self.resource_type, label=self.resource_label,
                              center=self.center, study=self.study,
                              community=self.community)

    def to_batch_op(self, action: Literal["grant", "revoke"]) -> BatchOperation:
        ...
```

- Frozen + field-based `__eq__`/`__hash__` means two `DesiredGrant`s with equal
  fields are equal and hash equally. Because the fields **are** the Structured
  Identity Tuple components (plus `user_id`), set difference on `DesiredGrant`
  keys on the tuple automatically. `flat_id` is not a field, so it cannot affect
  equality (Requirement 5.1–5.4).
- `__post_init__` rejects construction without a type or label (Requirement 3.2).
- `to_batch_op` builds a `BatchOperation` from the structured fields
  (Requirement 3.5).

#### `BatchOperation` (domain type, `authorization/models.py`)

Gains structured fields to match `DesiredGrant`:

```python
class BatchOperation(BaseModel):
    action: Literal["grant", "revoke"]
    user_id: str
    resource_type: str
    resource_label: str
    relation: str
    center: str | None = None
    study: str | None = None
    community: str | None = None
```

`client._execute_batch_chunk` builds each `BatchOperationModel` with a
`ResourceObject` from these fields.

### `authorization_sync/translator.py` (Requirement 3.3, 3.4, 3.6, 3.7)

`translate()` keeps calling `build_label_for_resource_prefix` (KEEP) to obtain
the label, then populates the `DesiredGrant` structured fields directly. It no
longer calls `build_resource_id` (flat assembly) on the grant path.

```python
label = build_label_for_resource_prefix(resource_prefix, resource_name)
for api_resource_type, relation in mapped_pairs:
    grants.add(DesiredGrant(
        user_id=registry_id,
        resource_type=api_resource_type,
        relation=relation,
        resource_label=label,
        center=center_group_id,   # None for general scope
        study=study_id,           # from StudyAuthorizations, else None
        community=None,           # grant path never targets community
    ))
```

- A parent field not applicable to the scope is left `None`, never a placeholder
  (Requirement 3.4).
- `build_label_for_resource_prefix` is extended to **reject** a prefix outside
  `{datatype, dashboard, page}` with an error, rather than silently returning the
  bare name, satisfying Requirement 3.7 while keeping the mapping of 3.6
  unchanged. (Current behavior returns `resource_name` for unknown prefixes; the
  grant path only ever passes the three known prefixes, so this tightening does
  not change produced labels.)
- `ACTIVITY_RELATION_MAP`, `validate_activity_relation_map`, `check_assignable`
  are unchanged (Requirement 9.1, 9.2, 10.3).

### `authorization_sync/sync_service.py`

`_entry_in_scope` already reads `entry.resource.center`/`entry.resource.community`
and treats `resource is None` as out-of-scope — this is the correct pattern and
is preserved (Requirement 6, 7). The change is in how current grants are turned
into `DesiredGrant`s for the diff:

```python
def _grants_in_scope(permissions, center_group_id):
    grants = set()
    for resource_type, entries in permissions.permissions.items():
        for entry in entries:
            if not _entry_in_scope(entry, center_group_id):
                continue                     # covers resource is None (Req 6, 7.5)
            r = entry.resource               # non-None here
            grants.add(DesiredGrant(
                user_id=permissions.user_id,
                resource_type=resource_type,
                relation=entry.relation,
                resource_label=r.label,
                center=r.center, study=r.study, community=r.community,
            ))
    return grants
```

- `to_grants(DesiredGrant)` (used to build the full `current` set) is updated via
  the new factory signature `(user_id, resource, relation)`; the `DesiredGrant`
  is built from `resource.label` + parents (structured), never from a flat id.
- `sync_users` continues to compute `grants_to_add = desired - current` and
  `grants_to_revoke = in_scope_current - desired`. Both operands are now keyed on
  the Structured Identity Tuple, so the diff no longer depends on reproducing the
  server flat id (Requirement 5).
- Scope selection, per-type query loop, batch apply, and partial-failure event
  reporting are unchanged (Requirement 7, 8.5, 9.5, 9.6).

### `authorization/client.py`

- `grant` / `revoke` / `check_permission`: build the request from
  `(resource_type, resource_label, center, study, community, relation)` and
  construct a `ResourceObject`; serialize via `request_dump`/`request_body` so no
  top-level `type`/`resourceId` and no `flat_id` are sent (Requirement 1).
- Their public signatures change from `(user_id, resource_type, resource_id,
  relation)` to accept the structured identity (either discrete parent params or
  a `ResourceObject`/`DesiredGrant`). The batch path passes structured
  `BatchOperation`s.
- Idempotent 409/404 result construction builds `GrantResult`/`RevokeResult` from
  the structured resource (echoing the request's `ResourceObject`) instead of
  `type`/`resource_id` (Requirement 8.1, 8.2).
- Batch chunking, `retry_on_503`, per-op `conflict`/`not_found` classification,
  and 503 retry are unchanged (Requirement 8.3, 8.4, 9.3, 9.4).
- `get_user_permissions` keeps the required `type` query parameter (ADR-015);
  the per-type loop still issues one request per type (Requirement 8.5, 8.6).

### Seed path and `set_resource_parents` (Requirement 10.4, 10.5)

`hierarchy_seeder` and `study_mapping` are on the **seed path**, which calls
`set_resource_parents` at `/resources/{type}/{resourceId}/parents`. Here
`{resourceId}` is a URL path segment, not a structured write body of the kind
Requirement 1 governs (grant/revoke/batch/permission-check). This design does
**not** migrate the seeder to a structured `resource` body: the parents endpoint
still identifies the resource by a path segment, and the requirements scope the
structured-`resource` write-body change to the four write-request models.

Consequently `build_resource_id` still has a live consumer (the seed path via
`study_mapping.__auth_resource_id*`), so per Requirement 10.5 it is **retained
unchanged**. It is removed from the grant path's import in `translator.py`. If
future work migrates the parents endpoint to accept a structured resource, the
seeder can adopt `ResourceObject` then; that is out of scope here.

## Data Models

### Corrected `ResourceObject`

```python
class ResourceObject(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str                                   # resource type
    label: str = Field(min_length=1)            # required identity core
    flat_id: str | None = Field(default=None, alias="flatId")  # read-only handle
    name: str | None = None                     # optional display/name
    study: str | None = None                    # parent field
    center: str | None = None                   # parent field
    community: str | None = None                # parent field
```

- `flat_id` present only on responses; excluded from request serialization.
- Parent-field combination validated per type.

### `DesiredGrant`

```python
@dataclass(frozen=True)
class DesiredGrant:
    user_id: str
    resource_type: str
    relation: str
    resource_label: str
    center: str | None = None
    study: str | None = None
    community: str | None = None
```

Frozen and hashable; its fields are exactly the Structured Identity Tuple
components plus `user_id`. No flat `resource_id` field.

## Diff design

The diff is the heart of the correctness argument. It must produce the same add
and remove sets as before the migration (Requirement 9.6) while keying on the
structured tuple.

### Deriving the tuple from each side

**Desired side (from a `DesiredGrant`):** the tuple is
`(resource_type, relation, resource_label, center, study, community)` — the
dataclass fields, read directly. Built by `translate()` from the label producer
and the scope's parent fields.

**Current side (from a `PermissionEntry`):** the entry's `resource` is the source
of truth. When `entry.resource is None`, the entry has no identity and is
**excluded** from the diff (skipped in both `to_grants` and `_grants_in_scope`) —
it appears in neither add nor revoke (Requirement 6). Otherwise the tuple is
`(resource_type, entry.relation, resource.label, resource.center, resource.study,
resource.community)`. `resource.flat_id` is deliberately ignored here.

### Why set difference is correct without flat_id

`DesiredGrant` is a frozen dataclass, so equality and hashing derive from its
fields. Two grants are equal iff `user_id` and all six identity components are
pairwise equal, and because every component is either a `str` compared
case-sensitively or `None` compared to `None`, this is exactly the tuple-equality
rule of Requirement 5.3 (absent equals only absent; `None != ""`).

Therefore:

- `grants_to_add = desired - current`: a desired grant survives iff no current
  grant shares its tuple → included in add, excluded from revoke (Requirement
  5.4, 5.5).
- `grants_to_revoke = in_scope_current - desired`: an in-scope current grant
  survives iff no desired grant shares its tuple → included in revoke, excluded
  from add (Requirement 5.6), subject to the scope filter (Requirement 7) and the
  None-resource exclusion (Requirement 6).

Because `flat_id` is not a field, a current grant carrying a server-assigned
`flat_id` that differs from anything the client could build still matches its
desired counterpart whenever the six components agree (Requirement 5.2). This is
the property the previous flat-string key failed: it required byte-for-byte
reproduction of the server id.

### Scope filtering (unchanged pattern, Requirement 7)

`_entry_in_scope` returns `False` when `entry.resource is None`, when
`entry.resource.community is not None`, or when `entry.resource.center` does not
equal the call's `center_group_id` (case-sensitive). Revocation candidates
(`in_scope_current`) are drawn only from entries passing this filter, so a sync of
one scope never revokes another scope's grants, community grants are never
revoked, and None-resource entries are never revoked — all read from structured
fields, never parsed from a flat string (Requirement 7.4).

## Error Handling

All error handling is **preserved**; the migration only changes how identity is
carried, not how failures are classified.

- **Idempotent single ops** (Requirement 8.1, 8.2): 409 on grant and 404 on
  revoke are treated as idempotent success, not retried, not raised. The
  synthesized `GrantResult`/`RevokeResult` is built from the request's structured
  `ResourceObject`.
- **Batch per-op classification** (Requirement 8.3, 8.4): per-operation
  `conflict`/`not_found` count as idempotent success and are excluded from the
  failure count; any other per-op error code counts as a failure. Governed by
  `_IDEMPOTENT_ERROR_CODES`, unchanged.
- **503 retry** (Requirement 9.3): `retry_on_503` with the same `max_retries` and
  `base_backoff` wraps every request as before.
- **Batch chunking** (Requirement 9.4): operations split into chunks of at most
  100 preserving order within and across chunks.
- **Catalog gap / None resource** (Requirement 6.4): when a current entry has
  `resource is None`, the sync logs a warning identifying the excluded entry as a
  catalog gap and completes the diff successfully; the entry is never revoked.
- **Partial batch failure reporting** (Requirement 9.5): non-idempotent failures
  are reported through the event collector identifying the failed operation;
  retry-on-503 behavior is left unchanged.
- **Pre-transmission validation** (Requirement 1.7): a write request built
  without a type, without a non-empty label, or with an invalid parent-field
  combination raises a validation error before any HTTP call.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all
valid executions of a system — essentially, a formal statement about what the
system should do. Properties serve as the bridge between human-readable
specifications and machine-verifiable correctness guarantees.*

This migration is a data-transformation and serialization change with clear
pure-function boundaries (model serialization, label parse/build, and a
set-based diff keyed on a tuple), so property-based testing applies. The
following properties consolidate the candidate properties in `requirements.md`
and add two surfaces they did not enumerate (per-type parent validation and
batch chunking).

### Property 1: Requests carry structured identity and never flat identity

*For any* `GrantRequest`, `RevokeRequest`, `BatchOperationModel`, or
`PermissionCheckRequest` built from a valid Structured Identity, the serialized
request payload contains a `resource` object whose `label` has at least one
character, and contains no `flat_id` key, no top-level `type` key, and no
top-level `resourceId` key.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.3, 2.4**

### Property 2: The diff round-trips on structured identity, independent of flat_id

*For any* set of valid desired grants, when the current grant set is constructed
from those same desired grants but with arbitrary (possibly differing)
server-assigned `flat_id` values, the computed `grants_to_add` and
`grants_to_revoke` are both empty. Equivalently, two grants are treated as the
same grant if and only if their Structured Identity Tuples
`(type, relation, label, center, study, community)` are pairwise equal
(case-sensitive strings; an absent component equals only an absent component),
regardless of any `flat_id`.

**Validates: Requirements 4.1, 4.2, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.6**

### Property 3: An entry with no structured resource is never revoked

*For any* current permission entry whose `resource` is `None`, the entry appears
in neither `grants_to_add` nor `grants_to_revoke` and does not participate in the
diff comparison; the diff comparison still completes with a success status.

**Validates: Requirements 4.3, 6.1, 6.2, 6.3, 6.4, 7.5**

### Property 4: Label split/rejoin round-trip

*For any* Resource Label of the form `{kind}-{name}` (including the `accepted`
special case that has no `-{name}` part, and names that themselves contain
hyphens), splitting the label into `kind` and `name` at the first `-` only and
rejoining them yields the original label unchanged.

Note: 3.6 is referenced here for the label form used by the Label Producers.

**Validates: Requirements 3.3, 3.6**

### Property 5: Community-scoped entries are never revoked

*For any* current permission entry whose structured `resource` carries a non-null
`community` field, the entry never appears in `grants_to_revoke`.

**Validates: Requirements 7.3**

### Property 6: Revoke candidacy is center-keyed

*For any* current permission entry with a non-null structured `resource` and no
`community` parent, the entry is a revoke candidate if and only if its
`resource.center` equals (exact, case-sensitive) the center group id being
reconciled.

**Validates: Requirements 7.1, 7.2, 7.4**

### Property 7: Parent-field combinations are valid per resource type

*For any* resource type and any combination of the parent fields
`study`/`center`/`community`, constructing a `ResourceObject` succeeds if and
only if that combination is permitted for the type — no parents for an
organization type; `(study+center)` or `(study)` for `data_pipeline`;
`(study+center)` or `(study)` or `(community)` for `dashboard`; `(study+center)`
or `(study)` or `(center)` or `(community)` for `page` — and an impermissible
combination is rejected with a validation error naming the type.

**Validates: Requirements 2.5, 2.6, 2.7, 2.8, 2.9**

### Property 8: Batch chunking preserves order and bounds chunk size

*For any* list of batch operations, splitting it into chunks yields chunks each
of at most 100 operations whose in-order concatenation equals the original list
exactly (order preserved within and across chunks).

**Validates: Requirements 9.4**

## Correctness Properties → design mapping

| Property | Design mechanism that guarantees it | PBT-suited |
|----------|-------------------------------------|------------|
| P1 — structured identity on requests | `ResourceObject.request_dump`/request models `request_body` exclude `flat_id` and emit only `resource` (no top-level `type`/`resourceId`); `label` has `min_length=1` | Yes |
| P2 — diff round-trips on identity | `DesiredGrant` frozen dataclass whose fields **are** the tuple; `flat_id` is not a field; `to_grants`/`_grants_in_scope` build from `resource` structured fields; `desired - current` / `in_scope_current - desired` | Yes |
| P3 — None resource never revoked | `to_grants` and `_grants_in_scope` skip `entry.resource is None`; `_entry_in_scope` returns False for None | Yes |
| P4 — label round-trip | Label form `{kind}-{name}` split at first `-`; `accepted` has no name part; produced only by the two Label Producers | Yes |
| P5 — community never revoked | `_entry_in_scope` returns False when `resource.community is not None` | Yes |
| P6 — center-keyed candidacy | `_entry_in_scope` compares `resource.center == center_group_id` (case-sensitive), reading from structured fields only | Yes |
| P7 — per-type parent validity | `ResourceObject.check_parent_fields` model-validator enforcing the per-type combination table | Yes |
| P8 — chunking invariant | `client.batch` slicing with `_BATCH_CHUNK_SIZE = 100`, order preserved | Yes |

Requirements verified by review or example rather than by a top-level property:
the mapping table of `build_label_for_resource_prefix` (3.6, example table);
unknown-prefix rejection (3.7, edge-case); idempotency of 409/404 and per-op
`conflict`/`not_found` (8.1–8.4, examples); one-request-per-type wiring
(8.5, 8.6, mock-based); constancy of `_SYNC_RESOURCE_TYPES` and
`ACTIVITY_RELATION_MAP` (9.1, 9.2, equality assertions); 503 retry (9.3,
mock-based); partial-failure reporting (9.5, mock-based); and the structural
targeted-migration constraints (10.1–10.5, review, with 10.5 decided by the
remaining-consumer check below). The verbatim `flat_id` echo on GET reads
(4.5, 4.6) is covered by an example/edge test.

## Testing Strategy

### Dual approach

- **Property tests** verify the eight universal properties above across many
  generated inputs. Use [Hypothesis](https://hypothesis.readthedocs.io/) (already
  the repo's PBT library; see `moto`-based tests and existing suites). Do not
  implement property-based testing from scratch.
- **Unit/example tests** verify specific examples, edge cases, and error
  conditions: the label-producer mapping table, unknown-prefix rejection,
  idempotent status-code handling, 503 retry, per-type query wiring, constancy of
  the activity map, and partial-failure reporting.

### Property test configuration

- Minimum **100 iterations** per property test (Hypothesis default `max_examples`
  is 100; set explicitly where a generator is expensive).
- Each property test is tagged with a comment referencing its design property:
  `# Feature: authorization-api-structured-resource-migration, Property N: <text>`.
- One property-based test implements each correctness property (P1–P8).
- Generators cover the tricky cases from the prework: labels with the `accepted`
  special case and hyphenated names (P4); `flat_id` values that differ from any
  client-derivable string (P2); parent-field combinations both valid and invalid
  per type (P7); mixes of in-scope, out-of-scope, community, and None-resource
  entries (P3, P5, P6); and operation lists spanning several chunk boundaries
  (P8).

### Test migration (existing suites use the old flat shape)

These existing tests assert the pre-migration flat identity and must be migrated
to the structured contract:

- `common/test/python/authorization/` — request/response model tests that expect
  top-level `type`/`resourceId` and a `ResourceObject.id`; client tests that build
  `grant`/`revoke`/`batch`/`check` with `resource_id=` and assert flat payloads.
  Update to assert a structured `resource` with `label`, no `flat_id` on requests,
  and identity read from `resource` on responses.
- `common/test/python/authorization_sync_test/` — `test_translator.py` (its
  `_build_resource_id` mirror and flat-id assertions) and sync-service diff tests
  keyed on flat `resource_id`. Re-key on the Structured Identity Tuple and assert
  structured `DesiredGrant` fields.
- `project_management` seeder tests — unaffected by the write-body change (the
  seed path is not migrated), but confirm they still pass since `build_resource_id`
  is retained.

### Conventions

- Python 3.12, Pydantic v2, run via the devcontainer / Pants (`pants_fix` →
  `pants_lint` → `pants_check` → `pants_test`). All imports at file top.
- New test files live under `_test`-suffixed directories per repo structure
  rules; reuse/extend the existing suites rather than creating parallel ones.
- Follow the run.py/main.py separation where gear entry points are touched; this
  migration is library-level and does not add gear entry points.

## Migration and removal plan

### `build_resource_id` (Requirement 10.5)

`build_resource_id` still has a live consumer after the migration: the **seed
path** in `common/src/python/projects/study_mapping.py`
(`__auth_resource_id` / `__auth_resource_id_no_center`), which builds the
`{resourceId}` path segment passed to `hierarchy_seeder.seed_*` →
`set_resource_parents`. Per Requirement 10.5 ("otherwise retain `build_resource_id`
unchanged"), `build_resource_id` is **kept unchanged**. It is only removed from
the grant path: `translator.py` stops importing and calling it. The
`authorization_sync/__init__.py` re-export is retained because the symbol remains
part of the package's public surface for the seed path.

### Hierarchy seeder (Requirement 10.4)

The seeder is **not** migrated to a structured `resource` write body. The parents
endpoint (`/resources/{type}/{resourceId}/parents`) identifies the resource by a
URL path segment, which is outside the four write-request models the
structured-`resource` contract governs. Existing Label Producers are reused for
every `resource.label` value; no new label-producing function is introduced.

### In-place edits and reuse (Requirement 10.1–10.3)

`ResourceObject`, `DesiredGrant`, the per-type query loop, batch chunking, retry
logic, and event reporting are edited in place — fields and input parameters
change, but the classes, module files, and their locations do not move or get
renamed. No additional request-side resource type is introduced.

### Versioning (out of scope)

No version bumps and no CHANGELOG entries are made as part of this migration;
versioning is handled separately on explicit request.
