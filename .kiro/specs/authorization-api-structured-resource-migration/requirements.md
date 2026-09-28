# Requirements Document

## Introduction

The NACC Authorization API was updated to route resource identity through a
single structured `resource` field (Increment 5 of the client migration notes).
This is a breaking change: requests must send identity in the structured
`resource` field and are rejected with an HTTP 400 if they send the legacy
top-level `type`/`resourceId` fields; responses carry identity only in the
structured `resource` field, exposing the flat identifier solely as the
read-only, opaque `resource.flat_id` handle.

The current authorization client library (`common/src/python/authorization/`)
and auth sync orchestration (`common/src/python/authorization_sync/`) do not
comply. They still send the removed top-level fields, model `ResourceObject`
with an `id` field the schema no longer has, key the desired-vs-current diff on
a client-reconstructed flat ID, and parse responses from the removed top-level
`resourceId`. As a result grant, revoke, and batch operations break against the
updated API.

This feature migrates the client models and sync code to the structured
`resource` contract. It is a targeted migration, not a rewrite: the module
layout, model classes, sync flow, label producers, scope-aware revocation, retry
behavior, batch chunking, and event reporting are all preserved; only what the
structured-`resource` contract forces is changed.

A recurring failure mode in prior work was confusing what constitutes resource
identity. These requirements therefore make resource identity precise and
unambiguous: identity is the structured tuple of type, label, and explicit
parent references, and the server-owned flat ID is never constructed, parsed, or
used as a matching key.

## Glossary

- **Authorization API**: The NACC Authorization service that stores user grants
  on resources, accessed through the client library in
  `common/src/python/authorization/`.
- **Auth Sync**: The orchestration in `common/src/python/authorization_sync/`
  that reconciles a user's grants by computing and applying a diff between
  desired and current grants.
- **Resource Type**: The category of a resource in the Authorization API (for
  example `data_pipeline`, `dashboard`, `page`, or an organization type). Sent
  as the `type` field on the structured `resource`.
- **Resource Label**: The resource-identifying core of a resource, independent
  of which center or study it belongs to, carried in `resource.label`. It has
  the form `{kind}-{name}` where `kind` is one of `ingest`, `sandbox`,
  `retrospective`, `distribution`, `accepted`, `dashboard`, `page`. The
  `accepted` kind stands alone with no `-{name}` part. A `name` may itself
  contain hyphens (for example `ingest-scan-analysis`), so a label is split into
  `kind` and `name` at the first `-` only.
- **Parent Fields**: The explicit parent references on a `resource`: `study`,
  `center`, and `community`. Which parent fields are permitted depends on the
  Resource Type (see Requirement 2).
- **Structured Identity**: The complete structured description of a resource:
  its Resource Type, Resource Label, and Parent Fields (`center`, `study`,
  `community`). This is the resource's identity — not a flat string.
- **Structured Identity Tuple**: The tuple used as the diff-matching key for a
  grant: (resource type, relation, resource label, center, study, community).
- **flat_id**: The read-only, opaque, server-owned flat identifier returned as
  `resource.flat_id` on responses. It is never sent on requests, never
  constructed by the client, and never parsed by the client. It may be echoed
  back verbatim (for example as a `{resourceId}` path segment on a GET read).
- **ResourceObject**: The Pydantic model in
  `common/src/python/authorization/models.py` representing a structured
  `resource`. One model is used for both requests and responses.
- **DesiredGrant**: The frozen dataclass in
  `common/src/python/authorization_sync/models.py` representing a grant the user
  should hold, used for set-based diffing.
- **Label Producer**: Code that builds a Resource Label. There are two:
  `build_label_for_resource_prefix` in
  `common/src/python/authorization_sync/translator.py` (grant path) and the
  inline label builder in `common/src/python/projects/study_mapping.py` (seed
  path).
- **Scope-Aware Revocation**: The logic in `sync_service._entry_in_scope` /
  `_grants_in_scope` that restricts revocation to grants belonging to the scope
  being reconciled.
- **ACTIVITY_RELATION_MAP**: The mapping in `translator.py` from an internal
  activity `(action, resource_prefix)` to Authorization API
  `(resource_type, relation)` pairs.

## Requirements

### Requirement 1: Structured resource on all write requests

**User Story:** As a maintainer of the auth sync gear, I want every write
request to carry a structured `resource`, so that the updated Authorization API
accepts grant, revoke, batch, and permission-check requests instead of
rejecting them with a 400.

#### Acceptance Criteria

1. WHEN a `GrantRequest`, a `RevokeRequest`, a `BatchOperationModel`, or a `PermissionCheckRequest` is serialized for transmission, THE Authorization API client SHALL include a structured `resource` field carrying the Structured Identity, where Structured Identity consists of the resource type, the resource label, and the applicable parent fields (center, study, community).
2. WHEN any write request is serialized for transmission, THE Authorization API client SHALL exclude the top-level `type` field and the top-level `resourceId` field from the request payload.
3. WHEN a `resource` object is serialized into a request payload, THE Authorization API client SHALL exclude the server-owned `flat_id` field from that payload.
4. WHEN a `resource` object is serialized into a request payload, THE Authorization API client SHALL include a `label` field whose value contains at least one character.
5. WHEN a `resource` object is serialized into a request payload, THE Authorization API client SHALL include a resource type value and every parent field (center, study, community) that applies to that resource type.
6. WHEN the `grant`, `revoke`, or `batch` client method is invoked with the Structured Identity of a grant, THE Authorization API client SHALL construct the request's `resource` object from the resource type, resource label, and applicable parent fields of that Structured Identity.
7. IF a write request is invoked without a resource type, without a non-empty `label`, or with any parent field required by the resource type absent, THEN THE Authorization API client SHALL reject the request before transmission and return an error indicating which Structured Identity component is missing, without sending any request to the Authorization API.

### Requirement 2: ResourceObject matches the API schema

**User Story:** As a developer using the authorization client, I want a single
`ResourceObject` that matches the API schema, so that the same model serializes
correctly on requests and parses correctly on responses without a request/response
split.

#### Acceptance Criteria

1. THE `ResourceObject` model SHALL define a required `label` field, and IF a `ResourceObject` is constructed or deserialized without a `label` value, THEN THE `ResourceObject` model SHALL reject the input with a validation error indicating that `label` is required.
2. THE `ResourceObject` model SHALL NOT define an `id` field, and IF input data supplied to `ResourceObject` construction or deserialization contains an `id` field, THEN THE `ResourceObject` model SHALL ignore the `id` field and exclude it from serialized output.
3. THE `ResourceObject` model SHALL define `flat_id` as an optional, read-only field that defaults to absent, is populated only when parsing a response, and is omitted from serialized request output.
4. WHEN a `ResourceObject` is serialized for a request, THE `ResourceObject` model SHALL exclude the `flat_id` field from the serialized output.
5. THE `ResourceObject` model SHALL define the fields `type`, `name`, `study`, `center`, and `community`, where `study`, `center`, and `community` are the Parent Fields and each is optional.
6. WHERE the Resource Type is an organization type, THE `ResourceObject` SHALL carry none of the Parent Fields `study`, `center`, or `community`, and IF any Parent Field is present, THEN THE `ResourceObject` model SHALL reject the input with a validation error indicating the Parent Fields are not permitted for the organization Resource Type.
7. WHERE the Resource Type is `data_pipeline`, THE `ResourceObject` SHALL carry exactly one of the following Parent Field combinations: `study` and `center` together, or `study` alone, and IF the present Parent Fields do not match one of these combinations, THEN THE `ResourceObject` model SHALL reject the input with a validation error indicating the Parent Field combination is invalid for the `data_pipeline` Resource Type.
8. WHERE the Resource Type is `dashboard`, THE `ResourceObject` SHALL carry exactly one of the following Parent Field combinations: `study` and `center` together, or `study` alone, or `community` alone, and IF the present Parent Fields do not match one of these combinations, THEN THE `ResourceObject` model SHALL reject the input with a validation error indicating the Parent Field combination is invalid for the `dashboard` Resource Type.
9. WHERE the Resource Type is `page`, THE `ResourceObject` SHALL carry exactly one of the following Parent Field combinations: `study` and `center` together, or `study` alone, or `center` alone, or `community` alone, and IF the present Parent Fields do not match one of these combinations, THEN THE `ResourceObject` model SHALL reject the input with a validation error indicating the Parent Field combination is invalid for the `page` Resource Type.

### Requirement 3: Structured identity carried through the sync

**User Story:** As a maintainer, I want the sync to carry structured identity
end to end, so that requests are built from the label and parent fields rather
than from a pre-built flat resource ID.

#### Acceptance Criteria

1. THE `DesiredGrant` dataclass SHALL carry the Structured Identity consisting of the Resource Type, the Resource Label, and the Parent Fields (`center`, `study`, `community`), and SHALL NOT carry a pre-built flat `resource_id` field.
2. IF a `DesiredGrant` is constructed without a Resource Label or without a Resource Type, THEN THE Auth Sync SHALL reject the construction and produce an error indicating the missing Structured Identity field, without producing a partial grant.
3. WHEN the translator maps a user's authorizations to desired grants, THE translator SHALL produce each `DesiredGrant` with the Resource Label obtained from a Label Producer, the Resource Type, and each applicable Parent Field, and SHALL NOT assemble a flat resource ID.
4. WHERE a Parent Field is not applicable to a given resource type, THE translator SHALL leave that Parent Field unset rather than substituting a placeholder value.
5. WHEN a `DesiredGrant` is converted to a batch operation, THE Auth Sync SHALL produce a batch operation whose `resource` object is built from that grant's Structured Identity, using the grant's Resource Type, Resource Label, and set Parent Fields.
6. THE `build_label_for_resource_prefix` Label Producer SHALL map the resource prefix to the label kind for exactly the following pairs: `datatype` → `ingest`, `dashboard` → `dashboard`, and `page` → `page`.
7. IF `build_label_for_resource_prefix` receives a resource prefix that is not one of `datatype`, `dashboard`, or `page`, THEN THE Label Producer SHALL reject the input and produce an error indicating an unsupported resource prefix, without emitting a label.

### Requirement 4: Responses parsed from the structured resource

**User Story:** As a developer consuming API responses, I want identity read
from the structured `resource` field, so that response parsing does not depend
on the removed top-level `resourceId`.

#### Acceptance Criteria

1. WHEN `UserPermissions.to_grants` builds grants from a response, THE Auth Sync SHALL read each entry's Structured Identity solely from the entry's `resource` field.
2. WHEN parsing a `PermissionEntry`, a `GrantResult`, a `RevokeResult`, a `ResourceParents`, or a `ResourceListItem`, THE Authorization API client SHALL read resource identity solely from the structured `resource` field.
3. IF a parsed response entry is missing the `resource` field or the `resource` field is null, THEN THE Authorization API client SHALL treat the entry as having no Structured Identity (see Requirement 6) rather than constructing a partial identity, and SHALL NOT fall back to a top-level `resourceId`.
4. WHEN identity is read from any response, THE Authorization API client SHALL NOT read, reference, or fall back to a top-level `resourceId` field for identity.
5. WHERE a `flat_id` value is present on a parsed response, THE Authorization API client SHALL treat it as an opaque handle and SHALL NOT parse, split, truncate, or otherwise decompose it to derive type, label, parent, or any other field.
6. WHEN a `flat_id` value is needed as a path segment for a GET read, THE Authorization API client SHALL echo the received `flat_id` value as an unmodified, byte-for-byte identical string.

### Requirement 5: Diff keyed on structured identity

**User Story:** As a maintainer, I want the desired-vs-current diff keyed on
structured identity, so that matching does not depend on the client reproducing
the server's flat ID byte-for-byte.

#### Acceptance Criteria

1. WHEN the Auth Sync computes `grants_to_add` and `grants_to_revoke`, THE Auth Sync SHALL compare desired grants against current grants using the Structured Identity Tuple (resource type, relation, resource label, center, study, community) as the sole matching key for both sides.
2. WHEN the Auth Sync computes the diff, THE Auth Sync SHALL NOT use `flat_id` as the matching key for any grant, including cases where a current grant carries a server-assigned `flat_id`.
3. WHEN the Auth Sync compares two Structured Identity Tuples, THE Auth Sync SHALL treat the tuples as equal only when all six components (resource type, relation, resource label, center, study, community) are pairwise equal, comparing each component by exact case-sensitive string equality and treating an absent component as equal only to another absent component.
4. WHEN a desired grant and a current grant have equal Structured Identity Tuples, THE Auth Sync SHALL treat them as the same grant and SHALL exclude that grant from both `grants_to_add` and `grants_to_revoke`.
5. WHEN a desired grant has no current grant with an equal Structured Identity Tuple, THE Auth Sync SHALL include that desired grant in `grants_to_add` and SHALL NOT include it in `grants_to_revoke`.
6. WHEN a current grant has no desired grant with an equal Structured Identity Tuple, THE Auth Sync SHALL include that current grant in `grants_to_revoke` and SHALL NOT include it in `grants_to_add`, subject to the scope and None-resource exclusions in Requirements 6 and 7.

### Requirement 6: Missing structured resource is never revoked

**User Story:** As a maintainer, I want entries with no structured `resource` to
be excluded from the diff, so that a catalog gap never causes an accidental
revocation.

#### Acceptance Criteria

1. IF a current permission entry has a `resource` value of None, THEN THE Auth Sync SHALL exclude that entry from the diff comparison such that the entry appears in neither `grants_to_add` nor `grants_to_revoke`.
2. IF a current permission entry has a `resource` value of None, THEN THE Auth Sync SHALL exclude that entry from `grants_to_revoke`, leaving the corresponding permission unchanged on the target.
3. WHEN the Auth Sync completes a diff comparison, THE Auth Sync SHALL revoke zero permission entries that had a `resource` value of None during that comparison.
4. WHEN the Auth Sync excludes a current permission entry with a `resource` value of None from the diff comparison, THE Auth Sync SHALL emit a log entry identifying the excluded entry and indicating a catalog gap, and SHALL complete the diff comparison with a success status.

### Requirement 7: Scope-aware revocation preserved

**User Story:** As a maintainer, I want scope-aware revocation to keep working,
so that a sync of one scope does not revoke grants belonging to another scope.

#### Acceptance Criteria

1. WHEN the Auth Sync selects revoke candidates, THE Auth Sync SHALL include a current grant in the revoke candidate set only if the grant's `resource.center` field value is exactly equal (case-sensitive string match) to the center group id being reconciled.
2. WHEN the Auth Sync evaluates a current grant whose `resource.center` field value is not equal to the center group id being reconciled, THE Auth Sync SHALL exclude that grant from the revoke candidate set and SHALL leave that grant unchanged.
3. IF a current permission entry carries a non-null `resource.community` field value, THEN THE Auth Sync SHALL exclude that entry from the revoke candidate set and SHALL leave that entry unchanged.
4. WHEN the Auth Sync reads an entry's scope, THE Auth Sync SHALL read `center` and `community` values directly from the entry's structured `resource` field and SHALL NOT derive, split, or parse those values from any flat identifier string.
5. IF an entry selected for scope evaluation has a missing or null `resource` field, THEN THE Auth Sync SHALL exclude that entry from the revoke candidate set and SHALL leave that entry unchanged, consistent with Requirement 6.

### Requirement 8: Idempotency and per-type querying preserved

**User Story:** As a maintainer, I want idempotent handling and per-type
querying preserved, so that repeated syncs stay safe and the permissions
endpoint contract (ADR-015) is respected.

#### Acceptance Criteria

1. WHEN the Authorization API returns HTTP 409 for a grant operation, THE Authorization API client SHALL record the grant as a successful idempotent grant, SHALL NOT retry the grant, and SHALL NOT raise an error to the caller.
2. WHEN the Authorization API returns HTTP 404 for a revoke operation, THE Authorization API client SHALL record the revoke as a successful idempotent revoke, SHALL NOT retry the revoke, and SHALL NOT raise an error to the caller.
3. WHEN a batch operation response includes a per-operation error code of `conflict` or `not_found`, THE Authorization API client SHALL count that individual operation as an idempotent success and SHALL exclude it from the failure count reported for the batch.
4. IF a batch operation response includes a per-operation error code other than `conflict` or `not_found`, THEN THE Authorization API client SHALL count that individual operation as a failure and SHALL include it in the failure count reported for the batch.
5. WHEN the Auth Sync queries current grants across all Resource Types, THE Auth Sync SHALL issue exactly one permissions request per Resource Type, each request including the required `type` query parameter set to that Resource Type.
6. IF a per-type permissions request omits or supplies an empty `type` query parameter, THEN THE Auth Sync SHALL NOT issue that request and SHALL report an error indicating the missing Resource Type identifier without recording any grants for that Resource Type.

### Requirement 9: Preserved behavior held constant

**User Story:** As a maintainer, I want unrelated behavior held constant, so
that the migration does not change what is synced or how failures are handled.

#### Acceptance Criteria

1. THE set of Resource Types synced SHALL remain exactly the set derived from `ACTIVITY_RELATION_MAP`, with no Resource Types added or removed by the migration.
2. THE `ACTIVITY_RELATION_MAP` activity-to-relation mappings SHALL remain unchanged, including the set of keys, the set of values, and each key-to-value association.
3. WHEN the Authorization API returns HTTP 503, THE Authorization API client SHALL retry the request using the existing retry-on-503 behavior, applying the same maximum retry count and back-off interval in effect before the migration.
4. WHEN the Auth Sync submits more than 100 operations in a single request, THE Authorization API client SHALL split them into chunks of at most 100 operations each, preserving the original submission order both within and across chunks.
5. IF a batch operation fails with a non-idempotent error, THEN THE Auth Sync SHALL report the failure through the event collector with an error indication identifying the failed operation, and SHALL leave the retry-on-503 behavior of criterion 3 unchanged.
6. THE general-scope and center-scope reconciliation semantics of `sync_user` and `sync_users` SHALL remain unchanged, producing the same set of add and remove operations for identical inputs as before the migration.

### Requirement 10: Targeted migration preserves existing structure

**User Story:** As a reviewer, I want the change scoped to what the contract
forces, so that the existing module layout and classes are reused rather than
replaced.

#### Acceptance Criteria

1. THE migration SHALL modify the existing `ResourceObject` type in place and SHALL NOT introduce any additional request-side resource type.
2. THE migration SHALL retain the existing module layout under `common/src/python/authorization/` and `common/src/python/authorization_sync/`, keeping the same set of module files and their locations unchanged except for edits to fields and inputs required by the contract.
3. THE migration SHALL reuse the existing `DesiredGrant` dataclass, per-type query loop, batch chunking, retry logic, and event reporting components without replacing or renaming them, modifying only their fields and input parameters.
4. THE migration SHALL reuse the existing Label Producers (`build_label_for_resource_prefix` and the `study_mapping.py` inline builder) to produce every `resource.label` value, and SHALL NOT introduce a new label-producing function.
5. IF `build_resource_id` (flat-ID assembly) has no remaining caller after the migration, THEN THE migration SHALL remove its definition; otherwise THE migration SHALL retain `build_resource_id` unchanged.

## Correctness Properties

These properties are candidates for property-based testing. Each holds for all
valid inputs of the stated shape.

1. **No flat_id or top-level identity on requests (round-trip / invariant).**
   For all `GrantRequest`, `RevokeRequest`, `BatchOperationModel`, and
   `PermissionCheckRequest` values, the serialized request payload contains no
   `flat_id` key, no top-level `type` key, and no top-level `resourceId` key,
   and contains a `resource` object with a non-empty `label`.

2. **Diff key round-trips on structured identity (round-trip / metamorphic).**
   For all sets of desired grants, when the current grant set is constructed
   from those same desired grants (with server-assigned `flat_id` values that
   differ from any client value), the computed `grants_to_add` and
   `grants_to_revoke` are both empty. Equivalently, two grants with equal
   Structured Identity Tuples are always treated as equal regardless of their
   `flat_id` values.

3. **None resource is never revoked (invariant).** For all response entries
   whose `resource` is None, the entry never appears in `grants_to_revoke` and
   never participates in the diff comparison.

4. **Label parse/build round-trip (round-trip).** For all Resource Labels of the
   form `{kind}-{name}` (including the `accepted` special case and names
   containing hyphens), splitting the label into `kind` and `name` at the first
   `-` and rejoining yields the original label.

5. **Community-scoped entries are never revoked (invariant).** For all current
   entries whose structured `resource` carries a non-null `community` field, the
   entry never appears in `grants_to_revoke`.

6. **Scope selection is center-keyed (metamorphic).** For all current entries
   with a non-null structured `resource` and no `community` parent, the entry is
   a revoke candidate if and only if its `resource.center` equals the center
   group id being reconciled.

## Out of Scope

- Version bumps and CHANGELOG entries. Versioning is handled separately on
  explicit request.
- The `PATCH /resources/{type}/{resourceId}` display-name endpoint and the
  `searchUserProfiles` client method are not adopted unless the sync work
  requires them.
- Documentation updates to `docs/processes/authorization-resource-ids.md` and
  the scoping section of `docs/user_management/index.md`, which are already
  updated; these are kept accurate only if the code changes shift where labels
  or parent fields are produced.
