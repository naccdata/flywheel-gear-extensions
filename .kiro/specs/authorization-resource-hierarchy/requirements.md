# Requirements Document

## Introduction

Integrate the project_management gear with the NACC Authorization API so that when the gear creates or manages projects and resources, it seeds the resource parent hierarchy in the Authorization Service. This enables inherited permissions — study admins automatically get `viewer` on child pipelines, center members get `viewer` on center-scoped dashboards, and community members get `viewer` on community-scoped pages. Without parent relationships, the OpenFGA computed relations produce no results and users would only have directly-granted permissions.

This feature depends on the shared client library defined in the `authorization-client-library` spec, which provides the `Authorization_Client` with typed models, SigV4 signing, and retry behavior.

## Glossary

- **Project_Management_Gear**: The Flywheel gear (`gear/project_management/`) that creates and manages projects based on study YAML configuration files.
- **Authorization_Client**: The shared Python client class (from `authorization-client-library`) that sends HTTP requests to the Authorization API with SigV4 signing.
- **Resource_Hierarchy_Seeder**: The component within the project_management gear responsible for calling the Authorization API to set parent relationships on resources.
- **Resource_Type**: A type in the authorization model — one of `data_pipeline`, `dashboard`, or `page`.
- **Resource_ID**: The identifier for a resource, derived from the Flywheel project label scheme.
- **Parent_Relationship**: A structural link from a resource to a parent organization (e.g., `parent_study`, `parent_center`, `parent_community`).
- **Center_Scoped_Resource**: A resource that belongs to both a study and a research center, requiring `parent_study` and `parent_center` relationships.
- **Study_Scoped_Resource**: A resource that belongs to a study only, requiring a `parent_study` relationship.
- **Community_Scoped_Resource**: A resource that belongs to the community, requiring a `parent_community` relationship. Identified by `level: "community"` in PageConfig.
- **Study_ID**: The identifier for a study (e.g., `adrc`, `clariti`, `dvcid`).
- **Center_ID**: The Flywheel group ID for a research center (e.g., `washington`, `upenn-ftld`).
- **Community_ID**: The identifier for the community organization (`nacc`).
- **StudyModel**: The Pydantic model representing a study configuration, containing study_id, centers, datatypes, dashboards, and pages.
- **StudyMappingVisitor**: The visitor class that traverses study configurations and creates Flywheel projects.

## Requirements

### Requirement 1: Set Parents for Center-Scoped Data Pipelines

**User Story:** As a platform administrator, I want center-scoped data pipelines to have their parent study and parent center set in the Authorization Service, so that study admins and center members automatically inherit viewer access to those pipelines.

#### Acceptance Criteria

1. WHEN the Project_Management_Gear creates or visits a center-scoped data pipeline, THE Resource_Hierarchy_Seeder SHALL call the Authorization_Client `set_resource_parents` method with resource type `data_pipeline`, the pipeline Resource_ID, and parent relationships: `parent_study` (parent type `study`, parent ID set to the Study_ID) and `parent_center` (parent type `research_center`, parent ID set to the Center_ID).
2. THE Resource_Hierarchy_Seeder SHALL use the Flywheel project label as the pipeline Resource_ID, where the label follows the pattern `{stage}-{datatype}{suffix}` with suffix empty for the primary study and `-{study_id}` for affiliated studies.

### Requirement 2: Set Parents for Center-Scoped Dashboards

**User Story:** As a platform administrator, I want center-scoped dashboards to have their parent study and parent center set in the Authorization Service, so that center members automatically inherit viewer access to those dashboards.

#### Acceptance Criteria

1. WHEN the Project_Management_Gear creates or visits a center-scoped dashboard during the StudyMappingVisitor center traversal, THE Resource_Hierarchy_Seeder SHALL call the Authorization_Client `set_parents` method with resource type `dashboard`, the dashboard Resource_ID, and parent relationships `parent_study` (with the Study_ID) and `parent_center` (with the Center_ID of the center being visited).
2. THE Resource_Hierarchy_Seeder SHALL derive the dashboard Resource_ID from the Flywheel project label using the pattern `dashboard-{name}{suffix}` where `name` is the dashboard name from the DashboardConfig, suffix is empty when the study `is_primary` is true, and suffix is `-{study_id}` otherwise.
3. IF the center is inactive, THEN THE Resource_Hierarchy_Seeder SHALL skip hierarchy seeding for dashboards in that center.

### Requirement 3: Set Parents for Study-Scoped Dashboards

**User Story:** As a platform administrator, I want study-scoped dashboards to have their parent study set in the Authorization Service, so that study members automatically inherit viewer access to those dashboards.

#### Acceptance Criteria

1. WHEN the Project_Management_Gear creates or visits a study-scoped dashboard (identified by DashboardConfig with `level` equal to `study`), THE Resource_Hierarchy_Seeder SHALL call the Authorization_Client `set_parents` method with resource type `dashboard`, the dashboard Resource_ID, and a single parent relationship with structural_relation `parent_study`, parent_type `study`, and parent_id set to the Study_ID.
2. THE Resource_Hierarchy_Seeder SHALL derive the dashboard Resource_ID using the pattern `dashboard-{name}{suffix}` where `name` is the DashboardConfig name field, suffix is empty when the StudyModel is the primary study, and suffix is `-{study_id}` when the StudyModel is an affiliated study.
3. IF the StudyModel contains no dashboards with `level` equal to `study`, THEN THE Resource_Hierarchy_Seeder SHALL skip study-scoped dashboard hierarchy seeding for that study without logging an error.

### Requirement 4: Set Parents for Study-Scoped Pages

**User Story:** As a platform administrator, I want study-scoped pages to have their parent study set in the Authorization Service, so that study members automatically inherit viewer access to those pages.

#### Acceptance Criteria

1. WHEN the Project_Management_Gear creates or visits a page whose PageConfig has `level` set to `study`, THE Resource_Hierarchy_Seeder SHALL call the Authorization_Client `set_parents` method with resource type `page`, the page Resource_ID, and a single parent relationship `parent_study` (with the Study_ID from the StudyModel).
2. THE Resource_Hierarchy_Seeder SHALL derive the page Resource_ID from the Flywheel project label using the pattern `page-{name}{suffix}` where `name` is the PageConfig `name` field, suffix is empty for the primary study (`study_type` is `primary`), and suffix is `-{study_id}` for affiliated studies (`study_type` is `affiliated`).
3. WHEN the Project_Management_Gear creates or visits a page whose PageConfig has `level` set to `community`, THE Resource_Hierarchy_Seeder SHALL NOT apply the study-scoped parent relationship to that page.

### Requirement 5: Set Parents for Community-Scoped Pages

**User Story:** As a platform administrator, I want community-scoped pages to have their parent community set in the Authorization Service, so that community members automatically inherit viewer access to those pages.

#### Acceptance Criteria

1. WHEN the Project_Management_Gear creates or visits a community-scoped page (identified by `level` value `community` in PageConfig), THE Resource_Hierarchy_Seeder SHALL call the Authorization_Client `set_parents` method with resource type `page`, the page Resource_ID, and exactly one parent relationship `parent_community` (with Community_ID `nacc`), excluding any `parent_study` or `parent_center` relationships.
2. THE Resource_Hierarchy_Seeder SHALL derive the page Resource_ID from the Flywheel project label using the pattern `page-{name}{suffix}` where suffix is empty for the primary study and `-{study_id}` for affiliated studies, consistent with the study context in which the page is defined.

### Requirement 6: Idempotent Execution

**User Story:** As a platform administrator, I want the hierarchy seeding to be safe to run on every project creation execution, so that re-running the gear does not cause errors or inconsistent state.

#### Acceptance Criteria

1. THE Resource_Hierarchy_Seeder SHALL call `set_parents` on every gear execution for each resource, regardless of whether the resource was newly created or already existed.
2. THE Resource_Hierarchy_Seeder SHALL NOT query the current parent state of a resource before calling `set_parents`.
3. WHEN the gear is executed multiple times for the same study configuration, THE parent relationships for each resource SHALL be identical to those set by a single execution.

### Requirement 7: Non-Blocking Error Handling

**User Story:** As a platform administrator, I want authorization service failures to not block project creation, so that the gear continues creating Flywheel projects even when the Authorization API is unavailable.

#### Acceptance Criteria

1. IF the Authorization_Client raises any exception when setting parents for a resource, THEN THE Resource_Hierarchy_Seeder SHALL catch the exception, log the error at error level, and continue processing the next resource independently.
2. IF the Authorization_Client raises any exception when setting parents for a resource, THEN THE Resource_Hierarchy_Seeder SHALL NOT raise an exception that stops the project creation workflow.
3. IF one or more `set_parents` calls failed during a gear run, THEN THE Resource_Hierarchy_Seeder SHALL log a warning at the end of the seeding pass indicating the count of resources that failed hierarchy seeding.

### Requirement 8: Scope Determination from Study Configuration

**User Story:** As a gear developer, I want the resource scope (center-scoped, study-scoped, or community-scoped) to be determined from the existing study YAML configuration, so that no new data sources are needed.

#### Acceptance Criteria

1. THE Resource_Hierarchy_Seeder SHALL determine dashboard scope using the `level` field from the DashboardConfig in the StudyModel (value `center` indicates center-scoped, value `study` indicates study-scoped, default `center` when dashboards are specified as plain strings without explicit level).
2. THE Resource_Hierarchy_Seeder SHALL determine page scope using the `level` field from the PageConfig in the StudyModel (value `center` indicates center-scoped, value `study` indicates study-scoped, value `community` indicates community-scoped).
3. WHEN the StudyMappingVisitor is iterating over a center in the StudyModel `centers` list, THE Resource_Hierarchy_Seeder SHALL treat all data pipelines created for that center as center-scoped resources.
4. IF a DashboardConfig or PageConfig has no explicit `level` value, THEN THE Resource_Hierarchy_Seeder SHALL treat the resource as center-scoped (using the model default of `center`).

### Requirement 9: Integration with Existing Project Creation Flow

**User Story:** As a gear developer, I want the hierarchy seeding to run as part of the existing project creation flow, so that it does not require a separate script or execution step.

#### Acceptance Criteria

1. WHEN the StudyMappingVisitor creates or visits a resource (data pipeline, dashboard, or page), THE Resource_Hierarchy_Seeder SHALL set the parent relationships for that resource within the same gear run, without requiring a separate script or invocation.
2. THE Resource_Hierarchy_Seeder SHALL receive the Authorization_Client instance via dependency injection so that tests can substitute a mock.

### Requirement 10: Logging

**User Story:** As a platform administrator, I want the hierarchy seeding to log its operations, so that I can diagnose issues and verify correct behavior.

#### Acceptance Criteria

1. WHEN a `set_parents` call succeeds, THE Resource_Hierarchy_Seeder SHALL log a message at debug level including the resource type, resource ID, and each parent relationship type with its organization ID.
2. IF a `set_parents` call fails, THEN THE Resource_Hierarchy_Seeder SHALL log a message at error level including the resource type, resource ID, and the exception description.

### Requirement 11: Authorization Client Dependency

**User Story:** As a gear developer, I want the Authorization_Client to be an optional dependency of the project_management gear, so that the gear can run without the Authorization Service configured.

#### Acceptance Criteria

1. IF no Authorization_Client is provided (value is None), THEN THE Project_Management_Gear SHALL skip all hierarchy seeding operations and log a single warning at gear startup indicating that authorization hierarchy seeding is disabled.
2. IF Authorization_Client creation fails due to missing or invalid configuration, THEN THE Project_Management_Gear SHALL treat the client as absent, skip all hierarchy seeding operations, and log an error at gear startup including the failure reason.
3. WHEN an Authorization_Client is successfully created, THE Project_Management_Gear SHALL pass the client instance to the Resource_Hierarchy_Seeder for use during the StudyMappingVisitor traversal.

### Requirement 12: Extend PageConfig to Support Community Level

**User Story:** As a gear developer, I want the PageConfig model to support a `community` level, so that community-scoped pages can be identified from the study YAML configuration.

#### Acceptance Criteria

1. THE PageConfig model SHALL accept `community` as a valid value for the `level` field, in addition to the existing `center` and `study` values.
2. WHEN a page is configured with `level` set to `community` (via dict format in YAML or direct PageConfig instantiation), THE PageConfig model SHALL pass validation without raising an error.
3. WHEN a page has `level` set to `community`, THE Project_Management_Gear SHALL classify the page as a Community_Scoped_Resource for hierarchy seeding, resulting in a `parent_community` relationship (as defined in Requirement 5).
4. WHEN pages are provided as a list of plain strings (without explicit level), THE PageConfig model SHALL continue to default the `level` to `center`.
