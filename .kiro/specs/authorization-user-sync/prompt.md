# Authorization User Sync — Spec Prompt

## Goal

Integrate the user_management gear with the NACC Authorization API so that when the gear processes user authorizations, it writes the corresponding grants to the Authorization Service in addition to its existing Flywheel role assignment.

This depends on the shared client library defined in the `authorization-client-library` spec.

## Context

### Authorization Model (types and relations)

The Authorization API enforces this model:

**Resource types relevant to user sync:**

- `data_pipeline` — relations: `viewer`, `submitter`, `auditor`
- `dashboard` — relations: `viewer`, `editor`
- `page` — relations: `viewer`

**Organization IDs:**

- `study`: the study_id — e.g., `adrc`, `clariti`, `dvcid`, `allftd`, `dlbc`
- `research_center`: the Flywheel group ID — e.g., `washington`, `upenn-ftld`, `columbia`
- `community`: `nacc` (single community for now)

### Resource ID Naming Convention

Resource IDs use the existing Flywheel project label scheme:

- `data_pipeline`: `{stage}-{datatype}{suffix}` — e.g., `ingest-form`, `ingest-form-dvcid`, `distribution-data-freeze`
- `dashboard`: `{name}{suffix}` — e.g., `adrc-reports`, `payment-tracker-clariti`
- `page`: `{name}{suffix}` — e.g., `community-resources`, `quick-access-link-generator`

Where `suffix` is empty for the primary study (adrc) and `-{study_id}` for affiliated studies.

### Gear's Current Authorization Model

The gear processes `DirectoryAuthorizations` from the NACC Directory (REDCap) and produces:

- `CenterUserEntry` with:
  - `registry_id` — the user's registry identifier (ePPN from CILogon), used as the user ID in the Authorization API
  - `study_authorizations: list[StudyAuthorizations]` — each has a `study_id` and activities
  - `authorizations: Authorizations` — general (non-center) activities
  - The center group ID (string, e.g., `washington`) is resolved by the caller via `CenterGroup`

- `Activity` = `action` + `Resource`:
  - Actions: `submit-audit`, `view`
  - Resources: `DatatypeResource(datatype)`, `DashboardResource(dashboard)`, `PageResource(page)`

### Activity-to-Relation Mapping

| Gear Action    | Resource Type       | Auth API Type   | Auth API Relation |
| -------------- | ------------------- | --------------- | ----------------- |
| `submit-audit` | `DatatypeResource`  | `data_pipeline` | `submitter`       |
| `view`         | `DatatypeResource`  | `data_pipeline` | `viewer`          |
| `view`         | `DashboardResource` | `dashboard`     | `viewer`          |
| `view`         | `PageResource`      | `page`          | `viewer`          |

`submitter` and `viewer` are independent relations in the OpenFGA schema — `submitter` does NOT imply `viewer`. The gear must grant both `submitter` and `viewer` when the user has `submit-audit`. When downgrading from `submit-audit` to `view`, the diff logic revokes `submitter` and keeps `viewer`.

### Sync Model

The gear's pattern is "here's a user, here's what they should have." There is no "replace all" endpoint — the API is grant/revoke based. The sync process:

1. Queries current grants via `GET /users/{userId}/permissions`
2. Computes the diff against desired state
3. Applies adds/revokes via `POST /grants/batch`

The 100-operation batch limit is not a concern for a single user (typical max ~30-50 grants). If it ever exceeds 100, the client chunks into multiple batch calls.

## Requirements

### 1. Activity-to-Grant Translator

A module that translates the gear's authorization vocabulary to the API's vocabulary:

- Maps `Activity` (action + resource) to `(type, relation)` pairs using a simple module-level constant (no external config file — the mapping is small and well-defined)
- Resolves resource IDs from study context (study_id, center group ID, datatype, etc.)
- Receives the already-resolved center group ID from the caller (does not perform adcid → group ID lookup itself)
- Handles the suffix logic (primary study = no suffix, affiliated = `-{study_id}`)
- Determines resource scope (center-scoped, study-scoped, general)

### 2. Authorization Sync Process

A process that, given a user (identified by `registry_id`) and their authorizations:

1. Translates the user's activities to the set of grants they should have
2. Queries the Authorization API for the user's current grants (via the client library)
3. Computes the diff (grants to add, grants to revoke)
4. Applies the diff via batch operations (via the client library)
5. Retries on transient failures (503); logs errors if retries are exhausted but does not block Flywheel processing

### 3. Integration with User Management Gear

Add the authorization sync as a step in the user processing pipeline:

- After the gear computes what a user should have (existing logic unchanged)
- Call the authorization sync process with the user's `registry_id` and translated grants
- The existing Flywheel role assignment continues unchanged (parallel output)
- Auth service sync retries on transient failures; if retries are exhausted, log the failure (the Portal depends on this data being current) but do not block Flywheel processing
- Failed syncs should be reported via the existing `UserEventCollector` pattern so operators have visibility

## Design Considerations

- The activity-to-relation mapping is a simple module-level constant (not externally configurable); refactor to config if it grows
- The sync process should support both full-sync (all users) and single-user sync
- Consider batching: the gear processes many users per run; batch API calls where possible
- The user ID in the Authorization API is the `registry_id` (ePPN from CILogon), passed as-is
- The center group ID (string) is passed to the translator by the caller — no adcid resolution needed in this layer
- No rate limiting concerns at current scale (hundreds of users, nightly runs, sequential batch calls)

## Dependencies

- Shared client library: `.kiro/specs/authorization-client-library`
- Resource hierarchy must be seeded by project_management gear before grants will inherit correctly: `.kiro/specs/authorization-resource-hierarchy`

## References

- Gear authorization logic: `common/src/python/users/authorization_visitor.py`, `user_processes.py`
- Study configuration: `data-platform-admin-tasks/data/studies/*/study.yaml`
- Project naming: `data-platform-admin-tasks/.kiro/steering/project-naming.md`
- Auth map (activity → Flywheel roles): `data-platform-admin-tasks/data/user-admin/authorizations.yaml`
- Authorization API OpenAPI spec: #[[file:openapi.yaml]]
