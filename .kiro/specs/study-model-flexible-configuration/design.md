# Design Document: Study Model Flexible Configuration

## Overview

This design refactors the `StudyModel` to support more flexible configuration by moving the mode from study-level to datatype-level and adding per-dashboard level configuration. The refactoring enables mixed-mode studies where different datatypes can have different modes (aggregation or distribution), and different dashboards can be created at different organizational levels (center or study), while maintaining backward compatibility with existing configurations.

The key changes include:
- Moving mode configuration from study-level to datatype-level
- Moving dashboard level configuration from study-level to per-dashboard
- Adding optional `funding_organization` field for funding organization tracking
- Updating project management logic to handle datatypes based on their individual modes
- Updating project management logic to handle dashboards based on their individual levels
- Providing migration path for existing study configurations

## Architecture

### Current Architecture

The current system has:
- `StudyModel`: Pydantic model with study-level `mode` field
- `StudyMappingVisitor`: Orchestrates project creation by selecting a single mapper based on study mode
- `AggregationMapper`: Creates projects for aggregation mode studies
- `DistributionMapper`: Creates projects for distribution mode studies

### Proposed Architecture

The refactored system will have:
- `StudyModel`: Enhanced with datatype-level mode configuration, per-dashboard level configuration, and `funding_organization` field
- `DatatypeConfig`: New model to encapsulate datatype name and mode
- `DashboardConfig`: New model to encapsulate dashboard name and level
- `StudyMappingVisitor`: Modified to iterate through datatypes and select mapper per-datatype, and to handle dashboards per-level
- `AggregationMapper`: Unchanged, but invoked per-datatype instead of per-study
- `DistributionMapper`: Unchanged, but invoked per-datatype instead of per-study

### Key Architectural Decisions

1. **Datatype Configuration Model**: Introduce a `DatatypeConfig` model to pair datatype names with their modes, providing type safety and validation.

2. **Dashboard Configuration Model**: Introduce a `DashboardConfig` model to pair dashboard names with their levels, providing type safety and validation.

3. **Backward Compatibility Strategy**: Maintain the study-level `mode` field as deprecated, with automatic migration to datatype-level modes during model validation. Similarly, maintain `dashboards` as a list of strings with automatic migration to dashboard-level configurations.

4. **Mapper Invocation**: Change from study-level mapper selection to datatype-level mapper invocation, allowing mixed-mode studies.

5. **Dashboard Creation**: Change from study-level dashboard creation to per-dashboard level handling, allowing mixed-level dashboards.

## Components and Interfaces

### StudyModel Changes

```python
class DatatypeConfig(BaseModel):
    """Configuration for a single datatype within a study."""
    
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )
    
    name: str
    mode: Literal["aggregation", "distribution"]


class DashboardConfig(BaseModel):
    """Configuration for a single dashboard within a study."""
    
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )
    
    name: str
    level: Literal["center", "study"] = "center"


class StudyModel(BaseModel):
    """Enhanced study model with datatype-level and dashboard-level configuration."""
    
    # Existing fields
    name: str = Field(alias="study")
    study_id: str
    centers: List[StudyCenterModel]
    study_type: Literal["primary", "affiliated"]
    legacy: bool = Field(True)
    published: bool = Field(False)
    pages: Optional[List[str]] = None
    
    # Modified fields
    datatypes: List[str] | List[DatatypeConfig]  # Support both formats
    dashboards: Optional[List[str] | List[DashboardConfig]] = None  # Support both formats
    mode: Optional[Literal["aggregation", "distribution"]] = None  # Deprecated
    
    # New fields
    funding_organization: Optional[str] = None
    
    # New methods
    def get_datatype_mode(self, datatype: str) -> Literal["aggregation", "distribution"]:
        """Get the mode for a specific datatype."""
        
    def get_datatype_configs(self) -> List[DatatypeConfig]:
        """Get all datatype configurations."""
        
    def get_datatypes_by_mode(self, mode: Literal["aggregation", "distribution"]) -> List[str]:
        """Get list of datatypes with the specified mode."""
        
    def get_dashboard_level(self, dashboard: str) -> Literal["center", "study"]:
        """Get the level for a specific dashboard."""
        
    def get_dashboard_configs(self) -> List[DashboardConfig]:
        """Get all dashboard configurations."""
        
    def get_dashboards_by_level(self, level: Literal["center", "study"]) -> List[str]:
        """Get list of dashboards with the specified level."""
```

### Validation Logic

The `StudyModel` will include validators to:

1. **Migrate legacy configurations**: Convert study-level mode to datatype-level modes, and list of dashboard strings to dashboard configurations
2. **Validate primary studies**: Ensure all datatypes in primary studies have aggregation mode
3. **Validate datatype completeness**: Ensure all datatypes have mode configuration
4. **Validate dashboard levels**: Ensure all dashboard levels are valid ("center" or "study")
5. **Handle mixed formats**: Support both `List[str]` and `List[DatatypeConfig]` for datatypes field, and both `List[str]` and `List[DashboardConfig]` for dashboards field

```python
@field_validator("datatypes", mode="before")
@classmethod
def normalize_datatypes(cls, value, info: ValidationInfo) -> List[DatatypeConfig]:
    """Normalize datatypes to DatatypeConfig list.
    
    Handles:
    - List[str] with study-level mode
    - List[DatatypeConfig]
    - Mixed formats
    """

@field_validator("dashboards", mode="before")
@classmethod
def normalize_dashboards(cls, value, info: ValidationInfo) -> Optional[List[DashboardConfig]]:
    """Normalize dashboards to DashboardConfig list.
    
    Handles:
    - List[str] (defaults to level "center")
    - List[DashboardConfig]
    - Mixed formats
    - None
    """
    
@model_validator(mode="after")
def validate_configuration(self) -> Self:
    """Validate complete study configuration.
    
    Checks:
    - Primary studies have aggregation-only datatypes
    - All datatypes have mode configuration
    - All dashboard levels are valid
    """
```

### StudyMappingVisitor Changes

The visitor will be modified to iterate through datatypes and select the appropriate mapper for each, and to handle dashboards based on their level:

```python
class StudyMappingVisitor(StudyVisitor):
    def visit_study(self, study: StudyModel) -> None:
        """Creates FW containers for the study."""
        # Group datatypes by mode
        aggregation_datatypes = study.get_datatypes_by_mode("aggregation")
        distribution_datatypes = study.get_datatypes_by_mode("distribution")
        
        # Create mappers for each mode if needed
        if aggregation_datatypes:
            agg_mapper = AggregationMapper(...)
            # Process aggregation datatypes
            
        if distribution_datatypes:
            dist_mapper = DistributionMapper(...)
            # Process distribution datatypes
            
        # Handle dashboards by level
        center_dashboards = study.get_dashboards_by_level("center")
        study_dashboards = study.get_dashboards_by_level("study")
        
        # Create center-level dashboards
        if center_dashboards:
            # Use existing dashboard creation logic
            pass
            
        # Skip study-level dashboards (not implemented yet)
        if study_dashboards:
            # Log that these are being skipped
            pass
```

### Mapper Interface Changes

The mappers will need minor modifications to accept datatype lists instead of using `study.datatypes`:

```python
class AggregationMapper(StudyMapper):
    def map_center_pipelines(
        self, 
        center: CenterGroup, 
        study_info: CenterStudyMetadata, 
        pipeline_adcid: int,
        datatypes: List[str]  # New parameter
    ) -> None:
        """Creates projects for specified datatypes."""
```

## Data Models

### DatatypeConfig

```python
class DatatypeConfig(BaseModel):
    """Configuration for a single datatype within a study.
    
    Attributes:
        name: The datatype name (e.g., "form", "dicom", "csv")
        mode: The mode for this datatype ("aggregation" or "distribution")
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )
    
    name: str
    mode: Literal["aggregation", "distribution"]
```

### DashboardConfig

```python
class DashboardConfig(BaseModel):
    """Configuration for a single dashboard within a study.
    
    Attributes:
        name: The dashboard name
        level: The organizational level for this dashboard ("center" or "study")
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )
    
    name: str
    level: Literal["center", "study"] = "center"
```

### StudyModel Field Changes

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `datatypes` | `List[str] \| List[DatatypeConfig]` | Yes | - | List of datatypes, supports both old and new formats |
| `dashboards` | `Optional[List[str] \| List[DashboardConfig]]` | No | None | List of dashboards, supports both old and new formats |
| `mode` | `Optional[Literal["aggregation", "distribution"]]` | No | None | Deprecated study-level mode |
| `funding_organization` | `Optional[str]` | No | None | Funding organization identifier |

### Serialization Format

Old format (backward compatible):
```yaml
study: NACC
study-id: nacc
mode: aggregation
datatypes:
  - form
  - dicom
  - csv
dashboards:
  - dashboard-a
  - dashboard-b
```

New format:
```yaml
study: NACC
study-id: nacc
datatypes:
  - name: form
    mode: aggregation
  - name: dicom
    mode: aggregation
  - name: csv
    mode: distribution
dashboards:
  - name: dashboard-a
    level: center
  - name: dashboard-b
    level: study
funding-organization: nih-niaaa
```

Mixed format (during migration):
```yaml
study: NACC
study-id: nacc
mode: aggregation  # Deprecated, will be applied to all datatypes
datatypes:
  - form
  - dicom
  - csv
dashboards:  # Old format, will default to level "center"
  - dashboard-a
  - dashboard-b
```


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: Datatype Mode Storage and Retrieval

For any StudyModel with datatype-level mode configurations, retrieving the mode for a specific datatype should return the mode that was configured for that datatype.

**Validates: Requirements 1.1, 1.5**

### Property 2: Datatype Mode Validation

For any datatype configuration with an invalid mode value (not "aggregation" or "distribution"), the StudyModel validation should reject the configuration with a validation error.

**Validates: Requirements 1.2**

### Property 3: Backward Compatible Mode Field

For any StudyModel created with the old study-level mode field and a list of datatype names, all datatypes should have the study-level mode applied to them.

**Validates: Requirements 1.3, 7.1**

### Property 4: Primary Study Aggregation-Only Validation

For any primary study configuration, if any datatype has mode "distribution", the StudyModel validation should raise a validation error.

**Validates: Requirements 1.4, 9.1**

### Property 5: Dashboard Level Validation

For any dashboard configuration with an invalid level value (not "center" or "study"), the StudyModel validation should reject the configuration with a validation error.

**Validates: Requirements 2.2**

### Property 6: Dashboard Level Storage and Retrieval

For any StudyModel with dashboard-level configurations, retrieving the level for a specific dashboard should return the level that was configured for that dashboard.

**Validates: Requirements 2.1, 2.6**

### Property 7: Dashboard Creation at Center Level

For any dashboard with level set to "center", the Project_Management should create that dashboard project in center groups.

**Validates: Requirements 2.4, 6.1**

### Property 8: Funding Organization Round Trip

For any StudyModel with a funding_organization value set, serializing and deserializing the model should preserve the funding_organization value.

**Validates: Requirements 3.1, 3.2**

### Property 9: Aggregation Mode Ingest Projects

For any datatype with mode "aggregation" in an active center, the Project_Management should create ingest projects for that datatype in the center group.

**Validates: Requirements 4.1**

### Property 10: Aggregation Mode Sandbox Projects

For any datatype with mode "aggregation" in an active center, the Project_Management should create sandbox projects for that datatype in the center group.

**Validates: Requirements 4.2**

### Property 11: Aggregation Mode Retrospective Projects

For any datatype with mode "aggregation" in a study with legacy data, the Project_Management should create retrospective projects for that datatype in center groups.

**Validates: Requirements 4.3**

### Property 12: Aggregation Mode Accepted Project

For any study with at least one datatype having mode "aggregation", the Project_Management should create an accepted project in center groups (shared across all aggregation datatypes).

**Validates: Requirements 4.4**

### Property 13: Published Study Release Infrastructure

For any published study with at least one aggregation mode datatype, the Project_Management should create a release group with a master project.

**Validates: Requirements 4.5**

### Property 14: Distribution Mode Center Projects

For any datatype with mode "distribution", the Project_Management should create distribution projects for that datatype in center groups.

**Validates: Requirements 5.1**

### Property 15: Distribution Mode Study Projects

For any datatype with mode "distribution", the Project_Management should create ingest projects for that datatype in the study group.

**Validates: Requirements 5.2**

### Property 16: Mixed Mode Independence

For any study with both aggregation and distribution mode datatypes, the Project_Management should create the correct project types for each datatype based on its individual mode.

**Validates: Requirements 5.3**

### Property 17: Primary Study Validation Preservation

For any primary study configuration that was valid before the refactoring, the enhanced StudyModel should continue to validate successfully.

**Validates: Requirements 7.3**

### Property 18: Backward Compatible Project Structure

For any study using the old configuration format (study-level mode), the Project_Management should produce the same project structure as it did before the refactoring.

**Validates: Requirements 7.4**

### Property 19: Datatype Configuration Serialization Round Trip

For any StudyModel with datatype-level mode configurations, serializing to JSON/YAML and then deserializing should produce an equivalent StudyModel with the same datatype modes.

**Validates: Requirements 8.1, 8.2**

### Property 20: Dashboard Configuration Serialization Round Trip

For any StudyModel with dashboard-level configurations, serializing to JSON/YAML and then deserializing should produce an equivalent StudyModel with the same dashboard levels.

**Validates: Requirements 8.3, 8.4**

### Property 21: Optional Fields Serialization Round Trip

For any StudyModel with funding_organization field set, serializing to JSON/YAML and then deserializing should preserve the field value.

**Validates: Requirements 8.5, 8.6**

### Property 22: Dashboard Level Default Migration

For any StudyModel with dashboards specified as a list of strings (old format), all dashboards should be assigned level "center" after deserialization.

**Validates: Requirements 8.8, 6.3**

### Property 23: Affiliated Study Mixed Mode Acceptance

For any affiliated study configuration with mixed modes (some datatypes aggregation, some distribution), the StudyModel validation should accept the configuration.

**Validates: Requirements 9.2**

### Property 24: Datatype Mode Completeness Validation

For any StudyModel where a datatype in the datatypes list does not have a corresponding mode configuration, the validation should raise an error.

**Validates: Requirements 9.3, 9.4**

### Property 25: Mixed Dashboard Levels

For any study with dashboards at different levels (some center, some study), the StudyModel should accept the configuration and correctly identify dashboards by level.

**Validates: Requirements 2.7, 6.4**

### Property 26: Aggregation Mapper Selection

For any study with mixed modes, when processing datatypes with mode "aggregation", the StudyMappingVisitor should use AggregationMapper to create projects.

**Validates: Requirements 10.1**

### Property 27: Distribution Mapper Selection

For any study with mixed modes, when processing datatypes with mode "distribution", the StudyMappingVisitor should use DistributionMapper to create projects.

**Validates: Requirements 10.2**

### Property 28: Single Mode Aggregation Backward Compatibility

For any study with only aggregation mode datatypes, the StudyMappingVisitor should produce the same project structure as the current implementation.

**Validates: Requirements 10.4**

### Property 29: Single Mode Distribution Backward Compatibility

For any study with only distribution mode datatypes, the StudyMappingVisitor should produce the same project structure as the current implementation.

**Validates: Requirements 10.5**

## Error Handling

### Validation Errors

The system will raise validation errors for:

1. **Invalid mode values**: Datatypes with mode values other than "aggregation" or "distribution"
2. **Primary study with distribution**: Primary studies with any datatype having mode "distribution"
3. **Missing mode configuration**: Datatypes without mode configuration
4. **Invalid dashboard level**: Dashboard level values other than "center" or "study"

### Migration Warnings

The system will log deprecation warnings for:

1. **Study-level mode usage**: When a configuration uses the deprecated study-level mode field
2. **Conflicting mode specifications**: When both study-level and datatype-level modes are present

### Project Creation Errors

The system will log errors for:

1. **Failed project creation**: When a project cannot be created in Flywheel
2. **Missing center groups**: When a center group is not found
3. **Invalid center metadata**: When center group metadata is malformed

Error handling will follow existing patterns in the codebase:
- Validation errors will be raised immediately during model creation
- Project creation errors will be logged but not halt processing of other projects
- Migration warnings will be logged at WARNING level

## Testing Strategy

### Dual Testing Approach

This feature will use both unit tests and property-based tests:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all inputs

Both are complementary and necessary for comprehensive coverage. Unit tests catch concrete bugs and verify specific scenarios, while property tests verify general correctness across a wide range of inputs.

### Property-Based Testing

We will use **Hypothesis** for Python property-based testing. Each property test will:
- Run a minimum of 100 iterations
- Reference its design document property in a comment
- Use the tag format: `# Feature: study-model-flexible-configuration, Property {number}: {property_text}`

Example property test structure:

```python
from hypothesis import given, strategies as st

# Feature: study-model-flexible-configuration, Property 1: Datatype Mode Storage and Retrieval
@given(
    datatypes=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=20),  # datatype name
            st.sampled_from(["aggregation", "distribution"])  # mode
        ),
        min_size=1,
        max_size=5
    )
)
@settings(max_examples=100)
def test_datatype_mode_retrieval(datatypes):
    """For any StudyModel with datatype configs, retrieving mode should return configured mode."""
    # Test implementation
```

### Unit Testing Focus

Unit tests will focus on:

1. **Specific migration scenarios**: Test concrete examples of old-to-new format migration
2. **Edge cases**: Empty datatype lists, single datatype, all same mode
3. **Error messages**: Verify validation error messages are clear and helpful
4. **Integration points**: Test interaction between StudyModel and mappers
5. **Backward compatibility examples**: Specific real-world study configurations

### Test Organization

Tests will be organized as:

```
common/test/python/projects_test/
├── test_study_model.py              # StudyModel unit tests
├── test_study_model_properties.py   # StudyModel property tests
├── test_study_mapping.py            # Existing mapper tests
├── test_study_mapping_mixed.py      # New mixed-mode tests
└── conftest.py                      # Shared fixtures
```

### Mock Strategy

We will create reusable mock fixtures for:

1. **FlywheelProxy**: Mock Flywheel client with sensible defaults
2. **CenterGroup**: Mock center groups with configurable metadata
3. **StudyModel**: Factory functions for creating test study configurations

Example fixture:

```python
@pytest.fixture
def mock_flywheel_proxy():
    """Reusable Flywheel proxy mock."""
    proxy = Mock()
    proxy.get_group.return_value = create_mock_group()
    proxy.find_group.return_value = create_mock_group_adaptor()
    return proxy

def create_study_config(
    study_type: str = "primary",
    datatypes: List[tuple[str, str]] = None,
    **kwargs
) -> dict:
    """Factory for creating study configurations."""
    if datatypes is None:
        datatypes = [("form", "aggregation")]
    
    return {
        "study": "test-study",
        "study-id": "test",
        "study-type": study_type,
        "datatypes": [
            {"name": name, "mode": mode} 
            for name, mode in datatypes
        ],
        **kwargs
    }
```

### Coverage Goals

- **Line coverage**: Minimum 90% for modified code
- **Branch coverage**: Minimum 85% for validation logic
- **Property test iterations**: Minimum 100 per property

### Testing Phases

1. **Phase 1**: Unit tests for StudyModel changes and validation
2. **Phase 2**: Property tests for StudyModel serialization and validation
3. **Phase 3**: Unit tests for mapper changes
4. **Phase 4**: Integration tests for mixed-mode project creation
5. **Phase 5**: Backward compatibility tests with real study configurations
