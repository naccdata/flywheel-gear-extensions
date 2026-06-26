# Requirements Document

## Introduction

This document specifies requirements for adding study-specific page resource support to the project management gear. The ADRC Portal uses Flywheel's authorization system by creating stub projects that represent portal pages. Currently, the project management gear creates study-related projects (ingest, distribution, dashboard) for centers, and dashboard resources were added in v2.3.0. This feature extends that pattern to support study-specific page resources, enabling the portal to control access to study-specific pages through Flywheel's project-based authorization.

## Glossary

- **Project_Management_Gear**: The Flywheel gear that creates groups and projects for NACC studies based on YAML configuration files
- **ADRC_Portal**: A UI extension layer on top of Flywheel that provides additional pages and dashboards
- **Stub_Project**: A Flywheel project created solely for authorization purposes, not for data storage
- **Study_Page**: A portal page that is study-specific and center-specific, created by the Project_Management_Gear
- **General_Page**: A portal page in the nacc group that is not study-specific, created manually (out of scope)
- **Center_Group**: A Flywheel group representing a research center
- **Study_Model**: The data model class that represents a NACC study configuration
- **Page_Resource**: An authorization resource representing access to a specific page type
- **Dashboard_Resource**: An authorization resource representing access to a specific dashboard type (existing feature)

## Requirements

### Requirement 1: Accept Page Configuration in Study Definition

**User Story:** As a NACC administrator, I want to specify page resources in study YAML files, so that study-specific pages can be created for centers.

#### Acceptance Criteria

1. WHEN a study YAML file contains a pages field, THE Study_Model SHALL accept the pages field as an optional list of strings
2. WHEN a study YAML file omits the pages field, THE Study_Model SHALL treat pages as an empty list
3. WHEN a study YAML file contains an empty pages list, THE Study_Model SHALL accept the empty list
4. THE Study_Model SHALL validate that each page name in the pages list is a non-empty string
5. FOR ALL valid study configurations with pages field, parsing the YAML SHALL produce a Study_Model object with the pages attribute set correctly

### Requirement 2: Create Page Stub Projects in Center Groups

**User Story:** As a NACC administrator, I want page stub projects created in center groups, so that the portal can control access to study-specific pages through Flywheel authorization.

#### Acceptance Criteria

1. WHEN a study has a pages field with one or more page names, THE Project_Management_Gear SHALL create a stub project for each page name in each active center group
2. WHEN creating a page stub project for a primary study, THE Project_Management_Gear SHALL use the label format "page-{page_name}"
3. WHEN creating a page stub project for an affiliated study, THE Project_Management_Gear SHALL use the label format "page-{page_name}-{study_id}"
4. WHEN a center is inactive, THE Project_Management_Gear SHALL NOT create page stub projects for that center
5. WHEN a study has no pages field, THE Project_Management_Gear SHALL NOT create any page stub projects
6. FOR ALL created page stub projects, the project SHALL exist in the center's Flywheel group with the correct label

### Requirement 3: Store Page Project Metadata

**User Story:** As a system integrator, I want page project metadata stored in center metadata, so that the user management gear can assign roles to page projects.

#### Acceptance Criteria

1. WHEN a page stub project is created, THE Project_Management_Gear SHALL store metadata in the center's metadata project
2. THE Page_Project_Metadata SHALL include the study_id field
3. THE Page_Project_Metadata SHALL include the project_id field
4. THE Page_Project_Metadata SHALL include the project_label field
5. THE Page_Project_Metadata SHALL include the page_name field
6. WHEN retrieving center metadata, THE System SHALL provide access to page project metadata by project label
7. FOR ALL page projects created, the metadata SHALL be retrievable from the center's metadata project

### Requirement 4: Support Visitor Pattern for Page Projects

**User Story:** As a developer, I want page projects to support the visitor pattern, so that the user management gear can process page projects consistently with other project types.

#### Acceptance Criteria

1. THE Page_Project_Metadata class SHALL implement an apply method that accepts an AbstractCenterMetadataVisitor
2. WHEN the apply method is called, THE Page_Project_Metadata SHALL invoke the visit_page_project method on the visitor
3. THE AbstractCenterMetadataVisitor interface SHALL define a visit_page_project abstract method
4. THE visit_page_project method SHALL accept a Page_Project_Metadata parameter
5. FOR ALL visitor implementations, calling apply on Page_Project_Metadata SHALL result in visit_page_project being invoked

### Requirement 5: Integrate Page Creation into Study Mapping

**User Story:** As a NACC administrator, I want page projects created automatically during study mapping, so that I don't need to manually create page stub projects.

#### Acceptance Criteria

1. WHEN the Study_Mapper processes a center for a study with pages, THE Study_Mapper SHALL create page projects before completing center pipeline mapping
2. WHEN the Study_Mapper creates page projects, THE Study_Mapper SHALL call the page creation method for each page name in the study's pages list
3. WHEN a page project is successfully created, THE Study_Mapper SHALL update the center study metadata with the page project information
4. WHEN a page project creation fails, THE Study_Mapper SHALL log an error message including the center ID and page project label
5. FOR ALL studies with pages field, processing the study SHALL result in page projects being created in all active center groups

### Requirement 6: Maintain Consistency with Dashboard Pattern

**User Story:** As a developer, I want page resource implementation to follow the same pattern as dashboard resources, so that the codebase remains consistent and maintainable.

#### Acceptance Criteria

1. THE Page_Project_Metadata class SHALL follow the same structure as Dashboard_Project_Metadata
2. THE page creation method SHALL follow the same pattern as the dashboard creation method
3. THE page_label method SHALL follow the same naming convention as the dashboard_label method
4. THE page project storage in Center_Study_Metadata SHALL follow the same pattern as dashboard project storage
5. FOR ALL page-related code, the implementation SHALL be structurally analogous to the corresponding dashboard code

### Requirement 7: Handle Multiple Pages Per Study

**User Story:** As a NACC administrator, I want to specify multiple page resources for a single study, so that different types of study-specific pages can have separate authorization.

#### Acceptance Criteria

1. WHEN a study specifies multiple page names in the pages list, THE Project_Management_Gear SHALL create a separate stub project for each page name
2. WHEN multiple page projects exist for a study, THE Center_Study_Metadata SHALL store all page projects in a dictionary keyed by project label
3. WHEN retrieving page project metadata, THE System SHALL support lookup by project label
4. FOR ALL page names in a study's pages list, a corresponding page project SHALL exist in each active center group
5. FOR ALL page projects in a center, the project labels SHALL be unique within that center group

### Requirement 8: Support Both Primary and Affiliated Studies

**User Story:** As a NACC administrator, I want page resources to work for both primary and affiliated studies, so that all study types can have study-specific pages.

#### Acceptance Criteria

1. WHEN a primary study has pages, THE Project_Management_Gear SHALL create page projects without a study suffix
2. WHEN an affiliated study has pages, THE Project_Management_Gear SHALL create page projects with the study_id suffix
3. WHEN a center participates in both primary and affiliated studies with pages, THE Project_Management_Gear SHALL create page projects for both studies with appropriate naming
4. FOR ALL primary study page projects, the label SHALL match the pattern "page-{page_name}"
5. FOR ALL affiliated study page projects, the label SHALL match the pattern "page-{page_name}-{study_id}"

