# Requirements Document

## Introduction

This feature refactors the StudyModel to support more flexible configuration by moving the mode from study-level to datatype-level and adding support for dashboard levels. Currently, a study has a single mode (aggregation or distribution) that applies to all datatypes. This refactoring enables mixed-mode studies where different datatypes can have different modes, and dashboards can be configured at different organizational levels.

The changes maintain backward compatibility with existing project management logic while enabling more granular control over study configuration.

## Glossary

- **StudyModel**: Pydantic data model representing a NACC study configuration
- **Mode**: Indicates whether data is aggregated from centers or distributed to centers (values: "aggregation" or "distribution")
- **Datatype**: Type of data collected in a study (e.g., "form", "dicom", "csv")
- **Dashboard**: Visualization project for study data
- **Dashboard_Level**: Organizational level where a specific dashboard is created (values: "center" or "study")
- **Center**: Research center participating in a study
- **Project_Management**: System that creates Flywheel groups and projects based on study configuration
- **AggregationMapper**: Component that creates projects for aggregation mode datatypes
- **DistributionMapper**: Component that creates projects for distribution mode datatypes
- **Funding_Organization**: Optional identifier for the funding organization associated with a study

## Requirements

### Requirement 1: Datatype-Level Mode Configuration

**User Story:** As a study administrator, I want to configure mode at the datatype level, so that I can have mixed-mode studies where some datatypes are aggregated and others are distributed.

#### Acceptance Criteria

1. THE StudyModel SHALL support a mode field on each datatype configuration
2. WHEN a StudyModel is created with datatype-level modes, THE StudyModel SHALL validate that each datatype has a valid mode value ("aggregation" or "distribution")
3. THE StudyModel SHALL maintain the existing study-level mode field for backward compatibility during migration
4. WHEN a primary study is configured, THE StudyModel SHALL validate that all datatype modes are set to "aggregation"
5. THE StudyModel SHALL provide a method to retrieve the mode for a specific datatype

### Requirement 2: Dashboard Level Configuration

**User Story:** As a study administrator, I want to specify the level for each dashboard individually, so that I can control which dashboards are created at the center level and which at the study level.

#### Acceptance Criteria

1. THE StudyModel SHALL support a level field on each dashboard configuration
2. WHEN a StudyModel is created with dashboard-level configurations, THE StudyModel SHALL validate that each dashboard has a valid level value ("center" or "study")
3. THE StudyModel SHALL maintain the existing dashboards field as a list of strings for backward compatibility during migration
4. WHEN a dashboard has level "center", THE Project_Management SHALL create that dashboard project in center groups
5. WHEN a dashboard has level "study", THE Project_Management SHALL skip creation of that dashboard (not implemented in this phase)
6. THE StudyModel SHALL provide a method to retrieve the level for a specific dashboard
7. THE StudyModel SHALL provide a method to retrieve dashboards by level


### Requirement 3: Funding Organization Field

**User Story:** As a study administrator, I want to record the funding organization identifier for a study, so that the study can be associated with the appropriate funding organization group.

#### Acceptance Criteria

1. THE StudyModel SHALL support an optional funding_organization field as a string
2. WHEN funding_organization is provided, THE StudyModel SHALL store the value in the model
3. THE Project_Management SHALL ignore the funding_organization field (no implementation needed in this phase)

### Requirement 4: Project Management Integration for Aggregation Mode Datatypes

**User Story:** As a system, I want to create appropriate projects for datatypes with aggregation mode, so that data can be collected from centers and aggregated.

#### Acceptance Criteria

1. WHEN a datatype has mode "aggregation", THE Project_Management SHALL create ingest projects for that datatype in center groups
2. WHEN a datatype has mode "aggregation", THE Project_Management SHALL create sandbox projects for that datatype in center groups
3. WHEN a datatype has mode "aggregation" and the study has legacy data, THE Project_Management SHALL create retrospective projects for that datatype in center groups
4. WHEN a datatype has mode "aggregation", THE Project_Management SHALL create an accepted project in center groups (shared across all aggregation datatypes)
5. WHEN a study is published and has aggregation mode datatypes, THE Project_Management SHALL create a release group with a master project


### Requirement 5: Project Management Integration for Distribution Mode Datatypes

**User Story:** As a system, I want to create appropriate projects for datatypes with distribution mode, so that data can be distributed to centers.

#### Acceptance Criteria

1. WHEN a datatype has mode "distribution", THE Project_Management SHALL create distribution projects for that datatype in center groups
2. WHEN a datatype has mode "distribution", THE Project_Management SHALL create ingest projects for that datatype in the study group
3. THE Project_Management SHALL handle distribution mode datatypes independently from aggregation mode datatypes within the same study

### Requirement 6: Dashboard Creation Based on Dashboard Level

**User Story:** As a system, I want to create dashboards at the appropriate organizational level based on each dashboard's configuration, so that visualizations are available where they are needed.

#### Acceptance Criteria

1. WHEN a dashboard has level "center", THE Project_Management SHALL create that dashboard project in center groups
2. WHEN a dashboard has level "study", THE Project_Management SHALL skip creation of that dashboard (deferred to future implementation)
3. WHEN a dashboard is specified without a level (old format), THE Project_Management SHALL default to creating it in center groups
4. THE Project_Management SHALL handle dashboards with different levels within the same study

### Requirement 7: Backward Compatibility with Existing Configurations

**User Story:** As a system administrator, I want existing study configurations to continue working without modification, so that the migration can be gradual.

#### Acceptance Criteria

1. WHEN a StudyModel is loaded with the old study-level mode field, THE StudyModel SHALL apply that mode to all datatypes
2. WHEN a StudyModel has both study-level and datatype-level modes, THE StudyModel SHALL use datatype-level modes and log a deprecation warning
3. THE StudyModel SHALL continue to support all existing validation rules for primary studies
4. THE Project_Management SHALL produce the same project structure for studies using the old configuration format


### Requirement 8: Data Model Serialization and Deserialization

**User Story:** As a system, I want to serialize and deserialize study configurations with the new fields, so that configurations can be stored and loaded correctly.

#### Acceptance Criteria

1. THE StudyModel SHALL serialize datatype configurations with mode information to JSON/YAML format
2. THE StudyModel SHALL deserialize datatype configurations with mode information from JSON/YAML format
3. THE StudyModel SHALL serialize dashboard configurations with level information to JSON/YAML format
4. THE StudyModel SHALL deserialize dashboard configurations with level information from JSON/YAML format
5. THE StudyModel SHALL serialize funding_organization field when present
6. THE StudyModel SHALL deserialize funding_organization field when present
7. WHEN deserializing a configuration without datatype-level modes, THE StudyModel SHALL apply the study-level mode to all datatypes
8. WHEN deserializing a configuration without dashboard-level configurations, THE StudyModel SHALL apply level "center" to all dashboards

### Requirement 9: Validation for Mixed-Mode Studies

**User Story:** As a system, I want to validate mixed-mode study configurations, so that invalid configurations are rejected early.

#### Acceptance Criteria

1. WHEN a primary study is configured with any datatype having mode "distribution", THE StudyModel SHALL raise a validation error
2. WHEN an affiliated study is configured with mixed modes, THE StudyModel SHALL accept the configuration
3. WHEN a datatype is configured without a mode, THE StudyModel SHALL raise a validation error
4. THE StudyModel SHALL validate that all datatypes in the datatypes list have corresponding mode configurations


### Requirement 10: Mapper Selection Based on Datatype Mode

**User Story:** As a system, I want to select the appropriate mapper for each datatype based on its mode, so that projects are created correctly for mixed-mode studies.

#### Acceptance Criteria

1. WHEN processing a study with mixed modes, THE StudyMappingVisitor SHALL use AggregationMapper for datatypes with mode "aggregation"
2. WHEN processing a study with mixed modes, THE StudyMappingVisitor SHALL use DistributionMapper for datatypes with mode "distribution"
3. THE StudyMappingVisitor SHALL iterate through datatypes and apply the appropriate mapper for each datatype's mode
4. WHEN a study has only aggregation mode datatypes, THE StudyMappingVisitor SHALL behave identically to the current implementation
5. WHEN a study has only distribution mode datatypes, THE StudyMappingVisitor SHALL behave identically to the current implementation
