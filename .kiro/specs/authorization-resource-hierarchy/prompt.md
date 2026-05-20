# Authorization Resource Hierarchy — Spec Prompt

## Goal

Integrate the project_management gear with the NACC Authorization API so that when the gear creates or manages projects/resources, it seeds the resource parent hierarchy in the Authorization Service. This enables inherited permissions (e.g., study admins automatically get `viewer` on child pipelines).

This depends on the shared client library defined in the `authorization-client-library` spec.

## Context

### Why Resource Hierarchy Matters

The Authorization API uses OpenFGA's hierarchical model. Computed relations (inherited permissions) only work when parent relationships are set:

- `data_pipeline.study_admin_access` — study admins get `viewer` on child pipelines
- `dashboard.site_viewer` — center members get `viewer` on center-scoped dashboards
- `dashboard.program_viewer` — study members get `viewer` on study-scoped dashboards
- `page.community_viewer` — community members get `viewer` on community-scoped pages

Without parent relationships, these computed relations produce no results — users would only have directly-granted permissions.

### Resource Scoping

Resources have different scopes that determine their parent hierarchy:

1. **Center-scoped (by study)** — most data pipelines and center-level dashboards
   - Parents: `parent_study` + `parent_center`
   - Example: pipeline `ingest-form` at center `washington` for study `adrc`

2. **Study-scoped** — study-level dashboards, some pages
   - Parents: `parent_study` only
   - Example: dashboard `enrollment-all-sites` for study `clariti`

3. **General/community-scoped** — community pages
   - Parents: `parent_community`
   - Example: page `community-resources`

### Resource ID Naming Convention

Resource IDs use the existing Flywheel project label scheme:

- `data_pipeline`: `{stage}-{datatype}{suffix}` — e.g., `ingest-form`, `ingest-form-dvcid`, `distribution-data-freeze`
- `dashboard`: `{name}{suffix}` — e.g., `adrc-reports`, `payment-tracker-clariti`
- `page`: `{name}{suffix}` — e.g., `community-resources`, `quick-access-link-generator`

Where `suffix` is empty for the primary study (adrc) and `-{study_id}` for affiliated studies.

### Organization IDs

- `study`: the study_id — e.g., `adrc`, `clariti`, `dvcid`, `allftd`, `dlbc`
- `research_center`: the Flywheel group ID — e.g., `washington`, `upenn-ftld`, `columbia`
- `community`: `nacc` (single community for now)

### API Endpoint

`PUT /resources/{type}/{resourceId}/parents` — sets parent organizations on a resource. This is idempotent (PUT replaces existing parents).

## Requirements

### Resource Hierarchy Seeding in project_management Gear

When the project_management gear creates a project, it should also set the resource's parent hierarchy in the Authorization API:

- Center-scoped pipelines: `parent_study` + `parent_center`
- Study-scoped dashboards: `parent_study`
- Center-scoped dashboards: `parent_study` + `parent_center`
- Community-scoped pages: `parent_community`
- Study-scoped pages: `parent_study`

The study YAML files (in data-platform-admin-tasks) contain all the information needed to derive these relationships. The project_management gear already knows the study config, center relationships, and creates the resources — this is the natural place.

### Behavior

- Call `PUT /resources/{type}/{resourceId}/parents` via the shared client library
- Idempotent: safe to call on every project creation run (PUT replaces existing parents)
- Should handle transient failures (503) with retry
- Log errors but do not block project creation on auth service failures

## Design Considerations

- The project_management gear already has the study and center context needed to determine resource scope and parents
- No new data sources are needed — the study YAML files already define the relationships
- This should run as part of the existing project creation flow, not as a separate script
- The PUT endpoint is idempotent, so re-running is safe (no need to check current state first)

## Dependencies

- Shared client library: `.kiro/specs/authorization-client-library`

## References

- Authorization API OpenAPI spec: #[[file:openapi.yaml]]
- Authorization model definition: `user-management/components/authorization-api/src/python/authorization_api/auth_model.py`
- OpenFGA schema: `user-management/components/authorization-service/models/schema.json`
- Study configuration: `data-platform-admin-tasks/data/studies/*/study.yaml`
- Project naming: `data-platform-admin-tasks/.kiro/steering/project-naming.md`
- Project management gear: `gear/project_management/`
