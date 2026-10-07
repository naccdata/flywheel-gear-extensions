# Authorization API — Structured Resource Migration for Auth Sync

## Context

We use the NACC Authorization API to synchronize user grants. The client
library lives in `common/src/python/authorization/` (models, client, transport)
and the sync orchestration lives in `common/src/python/authorization_sync/`
(sync service, translator, resource ID construction). The sync computes a diff
between the grants a user *should* hold (derived from their authorizations) and
the grants they *currently* hold (queried from the API), then applies the diff
through the batch endpoint.

The Authorization API was updated (see
`../user-management/docs/components/authorization-api/client-migration-notes.md`,
"Transition: Structured Resource Objects (Increment 5)"). Resource identity now
travels through a single structured `resource` field (a `ResourceObject`) on
both requests and responses. The change is breaking:

- **Requests** must send identity in the structured `resource` field. `resource`
  is **required on every request**. The legacy top-level `type` and `resourceId`
  fields are **rejected with a 400** if sent.
- **Responses** carry identity only in the structured `resource` field. There
  are no top-level `type`/`resourceId` fields to read. The flat identifier is
  available as the read-only `resource.flat_id` handle — a value you may echo
  back verbatim (e.g., as a `{resourceId}` path segment) but never construct or
  parse.

The **resource label** — the `label` field the structured `resource` now
carries — is already defined in this repo. See
`docs/processes/authorization-resource-ids.md`, which specifies the resource ID
format, the `{kind}-{name}` label form, its exceptions (e.g. `accepted` has no
`-{name}`; split on the *first* `-` only), and the two existing producers that
build labels. That definition does not change: what changes is that the label
now travels in `resource.label` instead of being concatenated into a flat ID.

Our current sync code does not comply, and grant/revoke/batch will fail against
the updated API. A prior review found:

1. **Requests still send removed fields (blocking).** `GrantRequest`,
   `RevokeRequest`, `BatchOperationModel`, and `PermissionCheckRequest` all
   extend a mixin that serializes top-level `type` + `resourceId` and never send
   a `resource` object. The updated API rejects these with a 400, so grant,
   revoke, and batch all break.
2. **`ResourceObject` schema mismatch.** Our `ResourceObject` has `id` and no
   `label`. The API schema uses `label` (required, "not the composite flat ID"),
   the parent fields (`study`/`center`/`community`), optional `name`, plus
   read-only `flat_id`. There is no `id` field.
3. **Identity is still routed through a client-constructed flat ID.**
   `resource_ids.build_resource_id` constructs `{center}_{label}-{study_id}` and
   the translator stores that in `DesiredGrant.resource_id`. The notes say to
   stop constructing/parsing flat IDs and send structured parent fields instead.
   Note the label *producers* stay useful — the label is still needed for
   `resource.label`; only the flat-ID *assembly* (`build_resource_id`) goes
   away on the request path.
4. **Response parsing reads removed fields.** `UserPermissions.to_grants` and
   `PermissionEntry.resource_id` read the top-level `resourceId` the notes say is
   gone from responses.
5. **Fragile diff key.** The diff compares `desired` (built from a locally
   constructed flat ID) against `current` (built from the response flat ID).
   These only match if our construction is byte-for-byte identical to the
   server's `flat_id`, which the notes explicitly warn against relying on.

The scope-aware revocation logic in `sync_service._entry_in_scope` already does
the right thing on the response side — it reads `entry.resource.center` and
`entry.resource.community` directly rather than parsing the flat ID. That is the
pattern to extend to the request side and the diff.

## What We Want

Update the authorization client models and the auth sync code to use the
structured `resource` field on all requests and responses, per Increment 5 of
the migration notes. After the change:

- Every write request (grant, revoke, batch operation, permission check) sends a
  structured `resource` object and does **not** send top-level `type`/`resourceId`.
- Every response is parsed from the structured `resource` field, using
  `resource.flat_id` only as an opaque echo handle.
- The desired-vs-current diff is keyed on structured identity (type, relation,
  and parent tuple, or the server-provided `flat_id` echoed from responses), not
  on a client-reconstructed flat ID.

**Reuse existing code wherever possible.** This is a targeted migration, not a
rewrite. Keep the current module layout, the existing model classes, and the
existing sync flow; change only what the structured-`resource` contract forces.
In particular, reuse rather than replace:

- The **resource label** definition and its producers —
  `build_label_for_resource_prefix` in `translator.py` and the label building in
  `projects/study_mapping.py` (both described in
  `docs/processes/authorization-resource-ids.md`). The label is still needed;
  feed it into `resource.label` instead of into `build_resource_id`.
- The scope-aware revocation logic (`_entry_in_scope` / `_grants_in_scope`),
  which already reads structured `resource` fields — extend the same pattern,
  don't reinvent it.
- The existing `ResourceObject` class (correct it in place rather than adding a
  parallel type, unless a distinct request/response split is genuinely needed).
- The `DesiredGrant` dataclass, the per-type query loop, batch chunking, retry,
  and event reporting — adjust their fields/inputs, keep their structure.

## Requirements

### Functional

1. **Request models carry structured `resource`.** Add a request-side
   `ResourceObject` (or reuse a corrected one) with `type`, `label`, optional
   `name`, and the conditional parent fields `study`/`center`/`community`.
   Change `GrantRequest`, `RevokeRequest`, `BatchOperationModel`, and
   `PermissionCheckRequest` to serialize identity as `resource` and to stop
   emitting top-level `type`/`resourceId`.

2. **`ResourceObject` matches the API schema.** Use `label` (required) rather
   than `id`. Keep `flat_id` as read-only (responses only). Keep `type`, `name`,
   `study`, `center`, `community`. Parent fields are conditional by type:
   - organization types: no parent fields
   - `data_pipeline`: `study` + `center`, or `study` alone
   - `dashboard`: `study` + `center`, `study` alone, or `community`
   - `page`: `study` + `center`, `study`, `center`, or `community`

3. **Carry structured identity through the sync.** Propagate `label` and the
   parent fields (`center`, `study`, `community`) through `DesiredGrant` and the
   translator instead of a pre-built flat `resource_id`. Build each request's
   `resource` object from those structured fields.

4. **Parse responses from `resource`.** Update `UserPermissions.to_grants`,
   `PermissionEntry`, `GrantResult`, `RevokeResult`, `ResourceParents`, and
   `ResourceListItem` handling to read the structured `resource` field. Treat
   `resource.flat_id` as the opaque key; do not read a top-level `resourceId`.

5. **Rework the diff key.** Ensure `grants_to_add` / `grants_to_revoke` compare
   desired and current grants on structured identity (or echoed `flat_id`), so
   the diff no longer depends on the client reconstructing the server's flat ID.

6. **Preserve scope-aware revocation.** The behavior in `_entry_in_scope` /
   `_grants_in_scope` (revoke only in-scope grants, never revoke when
   `resource` is None or when a community parent is present) must be retained.

7. **Preserve idempotency and per-type querying.** 409/404 idempotent handling
   in the client and the `?type=` per-request loop (ADR-015) must remain.

### Unchanged Behavior

- The set of resource types synced and the activity-to-relation mappings
  (`ACTIVITY_RELATION_MAP`) stay the same; only how identity is carried changes.
- Retry-on-503, batch chunking, and event-collector error reporting stay the
  same.
- The general vs. center scoping semantics of `sync_user` / `sync_users` stay
  the same.

## Key Files

- `common/src/python/authorization/models.py` — fix `ResourceObject` (`label`
  not `id`); add request-side structured resource; update `GrantRequest`,
  `RevokeRequest`, `BatchOperationModel`, `PermissionCheckRequest`,
  `PermissionEntry`, `UserPermissions.to_grants`, and the response models that
  read `resourceId`.
- `common/src/python/authorization/client.py` — build and send `resource` on
  grant/revoke/batch/check; stop sending top-level `type`/`resourceId`; read
  identity from `resource` on responses.
- `common/src/python/authorization_sync/models.py` — extend `DesiredGrant` to
  carry structured identity (label + parent fields) and produce batch ops with a
  `resource` object.
- `common/src/python/authorization_sync/translator.py` — keep
  `build_label_for_resource_prefix`; emit the label plus structured parent
  fields instead of a flat `resource_id`.
- `common/src/python/authorization_sync/resource_ids.py` — `build_resource_id`
  (flat-ID assembly) is no longer used on the request path; keep only if a
  consumer still needs it, otherwise remove. The resource-label definition it
  documents lives in `docs/processes/authorization-resource-ids.md`.
- `common/src/python/projects/study_mapping.py` — the seed-path label producer;
  reuse its labels for `resource.label` if the seeder is migrated.
- `common/src/python/authorization_sync/sync_service.py` — key the diff on
  structured identity / echoed `flat_id`; keep scope-aware revocation intact.
- `common/src/python/projects/hierarchy_seeder.py` — also constructs resource
  IDs and calls the client; verify it still works or migrate it too.

## Implementation Notes

- Read `docs/processes/authorization-resource-ids.md` first for the resource
  label definition (`{kind}-{name}`, its exceptions, and the two producers).
  Reuse that definition — the label still feeds `resource.label`.
- Start with the models and client request serialization (Requirements 1–4)
  since nothing else works until requests are accepted, then update the
  translator/`DesiredGrant`/diff (Requirements 3, 5).
- `flat_id` is read-only and opaque: echo it back as a path segment for GET
  reads, but never build or split it. Read `resource.center` / `resource.study`
  / `resource.community` directly for hierarchy.
- When the API returns no structured `resource` for an entry (catalog gap),
  preserve the existing safe default: treat it as out of scope so it is never
  revoked.
- Check existing tests under `common/test/python/authorization_sync_test/` and
  `common/test/python/authorization/` (and the project_management hierarchy
  seeder tests) — many construct requests/responses with the old flat-ID shape
  and will need updating to the structured `resource` form.
- Follow the repo's `run.py`/`main.py` separation and import conventions; keep
  business logic testable without live API calls.

## Out of Scope / Notes

- Do not bump version numbers or add CHANGELOG entries as part of this work;
  versioning is handled separately on explicit request.
- `docs/processes/authorization-resource-ids.md` and the scoping section of
  `docs/user_management/index.md` have already been updated to state that the
  flat ID is server-owned and clients do not construct it. Keep them accurate if
  the code changes shift where labels/parent fields are produced.
- The new `PATCH /resources/{type}/{resourceId}` display-name endpoint and the
  `searchUserProfiles` client method from the migration notes are additions we
  do not currently use; include them only if the sync work requires them.
