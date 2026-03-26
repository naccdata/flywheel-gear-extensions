# Design Document: Study Page Resources

## Overview

This design extends the project management gear to support study-specific page resources, following the same pattern established for dashboard resources in v2.3.0. The ADRC Portal uses Flywheel's project-based authorization system by creating stub projects that represent portal pages. This feature enables the portal to control access to study-specific pages through Flywheel's authorization model.

The implementation mirrors the dashboard resource pattern across three main components:
1. **StudyModel** - Accepts an optional `pages` field in study YAML configuration
2. **PageProjectMetadata** - Stores metadata for page stub projects in center metadata
3. **StudyMapper** - Creates page stub projects during study mapping

This design maintains consistency with the existing dashboard implementation, ensuring the codebase remains maintainable and predictable.

## Architecture

### Component Overview

The feature integrates into the existing project management architecture:

```
Study YAML Configuration
    ↓
StudyModel (study.py)
    ↓
StudyMapper (study_mapping.py)
    ↓
CenterGroup (center_group.py)
    ↓
PageProjectMetadata stored in Center Metadata
```

### Key Design Decisions

1. **Pattern Consistency**: Follow the exact same pattern as dashboard resources to maintain codebase consistency
2. **Naming Convention**: Use `page-{page_name}` for primary studies and `page-{page_name}-{study_id}` for affiliated studies
3. **Metadata Storage**: Store page project metadata in `CenterStudyMetadata.page_projects` dictionary, keyed by project label
4. **Visitor Pattern**: Implement visitor pattern support for page projects to enable consistent processing by user management gear

## Components and Interfaces

### 1. StudyModel Extension (study.py)

Add an optional `pages` field to the `StudyModel` class to accept page configuration from YAML files.

```python
class StudyModel(BaseModel):
    """Data model for studies based on the model used in the project-management
    gear.
    """
    
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=AliasGenerator(alias=kebab_case),
        extra="forbid",
    )

    name: str = Field(alias="study")
    study_id: str
    centers: List[StudyCenterModel]
    datatypes: List[str]
    dashboards: Optional[List[str]] = None
    pages: Optional[List[str]] = None  # NEW FIELD
    mode: Literal["aggregation", "distribution"]
    study_type: Literal["primary", "affiliated"]
    legacy: bool = Field(True)
    published: bool = Field(False)
```

**Changes**:
- Add `pages: Optional[List[str]] = None` field
- Field accepts a list of page names or None
- Pydantic validation ensures each page name is a non-empty string
- Empty list is treated the same as None (no pages)

### 2. PageProjectMetadata Class (center_group.py)

Create a new metadata class following the same structure as `DashboardProjectMetadata`.

```python
class PageProjectMetadata(ProjectMetadata):
    """Metadata for a page project of a center."""

    page_name: str

    def apply(self, visitor: AbstractCenterMetadataVisitor) -> None:
        visitor.visit_page_project(self)
```

**Location**: Add after `DashboardProjectMetadata` class definition (around line 508)

**Structure**:
- Inherits from `ProjectMetadata` (provides `study_id`, `project_id`, `project_label`)
- Adds `page_name` field to identify which page this project represents
- Implements `apply()` method for visitor pattern support

### 3. AbstractCenterMetadataVisitor Extension (center_group.py)

Add abstract method for visiting page projects.

```python
class AbstractCenterMetadataVisitor(ABC):
    """Abstract class for visitor objects for center metadata."""

    @abstractmethod
    def visit_center(self, center: "CenterMetadata") -> None:
        pass

    @abstractmethod
    def visit_study(self, study: "CenterStudyMetadata") -> None:
        pass

    @abstractmethod
    def visit_project(self, project: "ProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_distribution_project(
        self, project: "DistributionProjectMetadata"
    ) -> None:
        pass

    @abstractmethod
    def visit_ingest_project(self, project: "IngestProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_redcap_form_project(self, project: "REDCapFormProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_form_ingest_project(self, project: "FormIngestProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_dashboard_project(self, project: "DashboardProjectMetadata") -> None:
        pass

    @abstractmethod
    def visit_page_project(self, project: "PageProjectMetadata") -> None:  # NEW METHOD
        pass
```

**Changes**:
- Add `visit_page_project()` abstract method
- Accepts `PageProjectMetadata` parameter
- Follows same pattern as `visit_dashboard_project()`

### 4. CenterStudyMetadata Extension (center_group.py)

Add page project storage and accessor methods.

```python
class CenterStudyMetadata(BaseModel):
    """Metadata for study details within a participating center."""

    model_config = ConfigDict(
        populate_by_name=True, alias_generator=AliasGenerator(alias=kebab_case)
    )

    study_id: str
    study_name: str
    ingest_projects: Dict[str, (IngestProjectMetadata | FormIngestProjectMetadata)] = {}
    accepted_project: Optional[ProjectMetadata] = None
    dashboard_projects: Optional[Dict[str, DashboardProjectMetadata]] = {}
    page_projects: Optional[Dict[str, PageProjectMetadata]] = {}  # NEW FIELD
    distribution_projects: Dict[str, DistributionProjectMetadata] = {}

    # ... existing methods ...

    def add_page(self, project: PageProjectMetadata) -> None:  # NEW METHOD
        """Adds the page project to the study metadata.

        Args:
            project: the page project metadata
        """
        self.page_projects = (
            self.page_projects if self.page_projects is not None else {}
        )
        self.page_projects[project.project_label] = project

    def get_page(self, project_label: str) -> Optional[PageProjectMetadata]:  # NEW METHOD
        """Gets the page project metadata for the project label.

        Args:
            project_label: the project label
        Returns:
            the page project metadata for the project label
        """
        if self.page_projects is None:
            return None

        return self.page_projects.get(project_label, None)
```

**Changes**:
- Add `page_projects: Optional[Dict[str, PageProjectMetadata]] = {}` field
- Add `add_page()` method following same pattern as `add_dashboard()`
- Add `get_page()` method following same pattern as `get_dashboard()`
- Dictionary keyed by project label for efficient lookup

### 5. StudyMapper Extension (study_mapping.py)

Add page creation logic to the `StudyMapper` class.

#### 5.1 Add page_label() Method

```python
class StudyMapper(ABC):
    """Abstract class for mapping a study to Flywheel groups and projects."""

    def __init__(self, *, study: StudyModel, proxy: FlywheelProxy) -> None:
        self._study = study
        self._proxy = proxy

    @property
    def study(self):
        return self._study

    @property
    def proxy(self):
        return self._proxy

    # ... existing methods ...

    def dashboard_label(self, dashboard_name: str) -> str:
        return f"dashboard-{dashboard_name}{self.study.project_suffix()}"

    def page_label(self, page_name: str) -> str:  # NEW METHOD
        """Creates the label for a page project.
        
        Args:
            page_name: the name of the page
        Returns:
            the project label for the page
        """
        return f"page-{page_name}{self.study.project_suffix()}"
```

**Location**: Add after `dashboard_label()` method (around line 97)

#### 5.2 Add __add_page() Method

```python
    def __add_page(  # NEW METHOD
        self,
        center: CenterGroup,
        study_info: CenterStudyMetadata,
        page_name: str,
    ) -> None:
        """Adds a page project to the center group.
        
        Args:
            center: the center group
            study_info: the metadata object to track center projects
            page_name: the name of the page
        """

        def update_page(project: ProjectAdaptor) -> None:
            study_info.add_page(
                PageProjectMetadata(
                    study_id=self.study.study_id,
                    project_id=project.id,
                    project_label=project.label,
                    page_name=page_name,
                )
            )

        self.add_pipeline(
            center=center,
            pipeline_label=self.page_label(page_name),
            update_study=update_page,
        )
```

**Location**: Add after `__add_dashboard()` method (around line 125)

**Pattern**: Follows exact same structure as `__add_dashboard()`:
- Creates closure `update_page()` to update metadata
- Calls `self.add_pipeline()` with page label and update function
- Handles project creation and metadata storage

#### 5.3 Update map_center_pipelines() Method

```python
    def map_center_pipelines(
        self, center: CenterGroup, study_info: CenterStudyMetadata, pipeline_adcid: int
    ) -> None:
        """Maps the study to pipelines within a center.

        Args:
          center: the center group
          study_info: the metadata object to track center projects
        """
        if (
            center.is_active()
            and self.study.dashboards is not None
            and self.study.dashboards
        ):
            for dashboard_name in self.study.dashboards:
                self.__add_dashboard(
                    center=center, study_info=study_info, dashboard_name=dashboard_name
                )
        
        # NEW CODE BLOCK
        if (
            center.is_active()
            and self.study.pages is not None
            and self.study.pages
        ):
            for page_name in self.study.pages:
                self.__add_page(
                    center=center, study_info=study_info, page_name=page_name
                )
```

**Changes**:
- Add page creation logic after dashboard creation
- Check if center is active
- Check if study has pages defined
- Iterate through page names and create each page project
- Follows exact same pattern as dashboard creation

### 6. GatherIngestDatatypesVisitor Extension (center_group.py)

Add stub implementation for the new visitor method.

```python
class GatherIngestDatatypesVisitor(AbstractCenterMetadataVisitor):
    """Visitor to gather ingest datatypes from center metadata."""

    def __init__(self) -> None:
        self._datatypes = []

    @property
    def datatypes(self):
        return self._datatypes

    # ... existing methods ...

    def visit_dashboard_project(self, project: DashboardProjectMetadata) -> None:
        pass

    def visit_page_project(self, project: PageProjectMetadata) -> None:  # NEW METHOD
        """Visit page project (no-op for datatype gathering).
        
        Args:
            project: the page project metadata
        """
        pass
```

**Location**: Add after `visit_dashboard_project()` method (around line 832)

**Rationale**: Page projects don't contain datatypes, so this is a no-op implementation

## Data Models

### PageProjectMetadata

```python
class PageProjectMetadata(ProjectMetadata):
    """Metadata for a page project of a center.
    
    Attributes:
        study_id: The study identifier (inherited from ProjectMetadata)
        project_id: The Flywheel project ID (inherited from ProjectMetadata)
        project_label: The project label (inherited from ProjectMetadata)
        page_name: The name of the page this project represents
    """
    page_name: str
```

**Inheritance**: Inherits from `ProjectMetadata` which provides:
- `study_id: str`
- `project_id: str`
- `project_label: str`

### CenterStudyMetadata.page_projects

```python
page_projects: Optional[Dict[str, PageProjectMetadata]] = {}
```

**Structure**:
- Dictionary keyed by project label (e.g., "page-enrollment", "page-data-entry-nacc-ftld")
- Values are `PageProjectMetadata` instances
- Optional field, defaults to empty dict
- Initialized to empty dict if None when adding first page

### StudyModel.pages

```python
pages: Optional[List[str]] = None
```

**Structure**:
- Optional list of page name strings
- None if not specified in YAML
- Empty list treated same as None
- Each string is a page name (e.g., "enrollment", "data-entry")

## Example YAML Configuration

### Primary Study with Pages

```yaml
study: NACC Uniform Data Set
study-id: nacc-uds
mode: aggregation
study-type: primary
datatypes:
  - clinical
  - imaging
dashboards:
  - qc
  - enrollment
pages:
  - enrollment
  - data-entry
centers:
  - center-01
  - center-02
```

**Result**: Creates projects in each center:
- `page-enrollment`
- `page-data-entry`

### Affiliated Study with Pages

```yaml
study: NACC FTLD Module
study-id: nacc-ftld
mode: aggregation
study-type: affiliated
datatypes:
  - clinical
pages:
  - enrollment
  - data-entry
centers:
  - center-01
  - center-02
```

**Result**: Creates projects in each center:
- `page-enrollment-nacc-ftld`
- `page-data-entry-nacc-ftld`

## Integration Flow

### Study Mapping Process

```
1. Load study YAML → StudyModel with pages field
2. StudyMappingVisitor.visit_center() called for each center
3. StudyMapper.map_center_pipelines() called
4. For each page in study.pages:
   a. StudyMapper.__add_page() called
   b. StudyMapper.page_label() generates project label
   c. StudyMapper.add_pipeline() creates project
   d. update_page() closure stores PageProjectMetadata
5. CenterGroup.update_project_info() saves metadata
```

### Visitor Pattern Flow

```
1. User management gear creates visitor
2. Visitor implements visit_page_project() method
3. CenterMetadata.apply(visitor) called
4. For each study: CenterStudyMetadata.apply(visitor)
5. For each page project: PageProjectMetadata.apply(visitor)
6. PageProjectMetadata.apply() calls visitor.visit_page_project(self)
7. Visitor processes page project (e.g., assigns roles)
```


## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: YAML Parsing Round-Trip

For any valid StudyModel with a pages field, serializing to YAML and parsing back should produce an equivalent StudyModel with the same pages list.

**Validates: Requirements 1.1, 1.5**

### Property 2: Invalid Page Names Rejected

For any pages list containing invalid values (empty strings, None, non-string types), the StudyModel validation should reject the input and raise a validation error.

**Validates: Requirements 1.4**

### Property 3: Page Projects Created for All Pages

For any study with N page names and M active centers, the system should create exactly N × M page stub projects after study mapping completes.

**Validates: Requirements 2.1, 7.1, 7.4**

### Property 4: Primary Study Label Format

For any primary study and any page name, the generated project label should match the format "page-{page_name}" exactly.

**Validates: Requirements 2.2, 8.1, 8.4**

### Property 5: Affiliated Study Label Format

For any affiliated study with study_id and any page name, the generated project label should match the format "page-{page_name}-{study_id}" exactly.

**Validates: Requirements 2.3, 8.2, 8.5**

### Property 6: Inactive Centers Excluded

For any study with pages and any inactive center, no page stub projects should be created for that inactive center.

**Validates: Requirements 2.4**

### Property 7: Page Projects Exist in Flywheel

For any page project that should be created (based on study configuration and active centers), a corresponding project with the correct label should exist in the center's Flywheel group.

**Validates: Requirements 2.6**

### Property 8: Metadata Storage and Retrieval

For any page project created with a given project label, storing the PageProjectMetadata and then retrieving it by that label should return the same metadata.

**Validates: Requirements 3.1, 3.6, 3.7, 7.3**

### Property 9: PageProjectMetadata Structure

For any PageProjectMetadata instance, it should contain all required fields: study_id, project_id, project_label, and page_name, all with non-empty string values.

**Validates: Requirements 3.2, 3.3, 3.4, 3.5**

### Property 10: Visitor Pattern Invocation

For any AbstractCenterMetadataVisitor implementation and any PageProjectMetadata instance, calling apply() on the metadata should result in the visitor's visit_page_project() method being invoked with that metadata.

**Validates: Requirements 4.2, 4.5**

### Property 11: Page Projects Created During Mapping

For any study with pages and any active center, after map_center_pipelines() completes, all page projects should exist and have metadata stored in CenterStudyMetadata.

**Validates: Requirements 5.1, 5.3, 5.5**

### Property 12: Page Creation Method Called for Each Page

For any study with N pages, processing that study for a center should result in the page creation method being called exactly N times.

**Validates: Requirements 5.2**

### Property 13: Error Logging on Failure

For any page project creation that fails, an error message containing both the center ID and the page project label should be logged.

**Validates: Requirements 5.4**

### Property 14: Multiple Page Projects Stored

For any study with multiple page names, all page projects should be stored in the CenterStudyMetadata.page_projects dictionary, each keyed by its unique project label.

**Validates: Requirements 7.2**

### Property 15: Unique Project Labels

For any center group, all page project labels within that center should be unique (no duplicate labels).

**Validates: Requirements 7.5**

### Property 16: Multiple Study Types Handled

For any center participating in both a primary study with pages and an affiliated study with pages, page projects should be created for both studies with correct naming (primary without suffix, affiliated with suffix).

**Validates: Requirements 8.3**

## Error Handling

### Validation Errors

**Invalid Page Names**:
- Empty strings in pages list → Pydantic ValidationError
- Non-string values in pages list → Pydantic ValidationError
- Null/None values in pages list → Pydantic ValidationError

**Error Message Format**: Pydantic provides detailed validation error messages indicating the field and validation rule that failed.

### Project Creation Errors

**Flywheel API Failures**:
- Network errors during project creation
- Permission errors when creating projects
- Duplicate project label conflicts

**Handling Strategy**:
- Log error with center ID and project label
- Continue processing other pages/centers
- Do not fail entire study mapping on single project failure

**Error Message Format**:
```
Failed to create page project {project_label} for center {center_id}: {error_details}
```

### Metadata Storage Errors

**Metadata Update Failures**:
- Flywheel API errors when updating metadata project
- Serialization errors when converting metadata to JSON

**Handling Strategy**:
- Log error with full context
- Raise exception to prevent partial state
- Ensure transactional semantics where possible

### Edge Cases

**Empty Pages List**:
- Treated same as None (no pages)
- No projects created
- No errors raised

**Inactive Centers**:
- Silently skipped during page project creation
- No error messages (expected behavior)
- Logged at debug level if needed

**Missing Metadata Project**:
- Should not occur in normal operation
- If occurs, raise CenterError with descriptive message
- Indicates configuration problem that needs resolution

## Testing Strategy

### Unit Testing

Unit tests focus on specific components and edge cases:

**StudyModel Tests** (`test_study.py`):
- Test parsing YAML with pages field
- Test parsing YAML without pages field
- Test parsing YAML with empty pages list
- Test validation rejects invalid page names
- Test validation rejects non-string values

**PageProjectMetadata Tests** (`test_center_group.py`):
- Test PageProjectMetadata creation with all fields
- Test visitor pattern apply() method
- Test serialization/deserialization

**CenterStudyMetadata Tests** (`test_center_group.py`):
- Test add_page() method
- Test get_page() method
- Test page_projects dictionary initialization
- Test multiple pages storage

**StudyMapper Tests** (`test_study_mapping.py`):
- Test page_label() method for primary studies
- Test page_label() method for affiliated studies
- Test __add_page() method
- Test map_center_pipelines() with pages
- Test map_center_pipelines() without pages
- Test error handling on project creation failure

### Property-Based Testing

Property tests verify universal properties across all inputs using a property-based testing library (e.g., Hypothesis for Python). Each test should run minimum 100 iterations.

**Test Configuration**:
- Library: Hypothesis
- Minimum iterations: 100 per test
- Tag format: `# Feature: study-page-resources, Property {N}: {description}`

**Property Test Suite**:

1. **YAML Round-Trip Property**
   - Generate random StudyModel instances with pages
   - Serialize to YAML and parse back
   - Verify pages field matches original
   - Tag: `Feature: study-page-resources, Property 1: YAML Parsing Round-Trip`

2. **Invalid Input Rejection Property**
   - Generate random invalid pages lists (empty strings, None, numbers)
   - Verify validation raises error
   - Tag: `Feature: study-page-resources, Property 2: Invalid Page Names Rejected`

3. **Project Count Property**
   - Generate random studies with N pages and M active centers
   - Run study mapping
   - Verify exactly N × M projects created
   - Tag: `Feature: study-page-resources, Property 3: Page Projects Created for All Pages`

4. **Primary Label Format Property**
   - Generate random primary studies with random page names
   - Verify all labels match "page-{page_name}" format
   - Tag: `Feature: study-page-resources, Property 4: Primary Study Label Format`

5. **Affiliated Label Format Property**
   - Generate random affiliated studies with random page names
   - Verify all labels match "page-{page_name}-{study_id}" format
   - Tag: `Feature: study-page-resources, Property 5: Affiliated Study Label Format`

6. **Inactive Center Exclusion Property**
   - Generate random studies with pages and mix of active/inactive centers
   - Verify no projects created for inactive centers
   - Tag: `Feature: study-page-resources, Property 6: Inactive Centers Excluded`

7. **Flywheel Project Existence Property**
   - Generate random page projects
   - Create in Flywheel
   - Verify projects exist with correct labels
   - Tag: `Feature: study-page-resources, Property 7: Page Projects Exist in Flywheel`

8. **Metadata Round-Trip Property**
   - Generate random PageProjectMetadata instances
   - Store and retrieve by label
   - Verify retrieved metadata matches original
   - Tag: `Feature: study-page-resources, Property 8: Metadata Storage and Retrieval`

9. **Metadata Structure Property**
   - Generate random PageProjectMetadata instances
   - Verify all required fields present and non-empty
   - Tag: `Feature: study-page-resources, Property 9: PageProjectMetadata Structure`

10. **Visitor Pattern Property**
    - Generate random PageProjectMetadata and visitor implementations
    - Call apply() and verify visit_page_project() invoked
    - Tag: `Feature: study-page-resources, Property 10: Visitor Pattern Invocation`

11. **Mapping Completion Property**
    - Generate random studies with pages
    - Run map_center_pipelines()
    - Verify all page projects exist with metadata
    - Tag: `Feature: study-page-resources, Property 11: Page Projects Created During Mapping`

12. **Method Call Count Property**
    - Generate random studies with N pages
    - Mock page creation method
    - Verify method called exactly N times
    - Tag: `Feature: study-page-resources, Property 12: Page Creation Method Called for Each Page`

13. **Error Logging Property**
    - Generate random page project creation failures
    - Verify error messages contain center ID and label
    - Tag: `Feature: study-page-resources, Property 13: Error Logging on Failure`

14. **Multiple Pages Storage Property**
    - Generate random studies with multiple pages
    - Verify all stored in dictionary with correct keys
    - Tag: `Feature: study-page-resources, Property 14: Multiple Page Projects Stored`

15. **Label Uniqueness Property**
    - Generate random page projects for a center
    - Verify all labels are unique
    - Tag: `Feature: study-page-resources, Property 15: Unique Project Labels`

16. **Multiple Study Types Property**
    - Generate random centers with both primary and affiliated studies
    - Verify correct naming for both study types
    - Tag: `Feature: study-page-resources, Property 16: Multiple Study Types Handled`

### Integration Testing

Integration tests verify the complete workflow:

**End-to-End Study Mapping Test**:
- Create test study YAML with pages field
- Run complete study mapping process
- Verify page projects created in Flywheel
- Verify metadata stored correctly
- Verify visitor pattern works with user management gear

**Multi-Study Integration Test**:
- Create primary study with pages
- Create affiliated study with pages
- Map both studies to same center
- Verify correct project labels for both
- Verify no label conflicts

**Error Recovery Test**:
- Simulate Flywheel API failures
- Verify error logging
- Verify partial success (other pages still created)
- Verify system remains in consistent state

### Test Data Builders

Create reusable builders for test data:

```python
class StudyModelBuilder:
    """Builder for creating test StudyModel instances."""
    
    def __init__(self):
        self._name = "Test Study"
        self._study_id = "test-study"
        self._centers = ["center-01"]
        self._datatypes = ["clinical"]
        self._pages = None
        self._mode = "aggregation"
        self._study_type = "primary"
    
    def with_pages(self, pages: List[str]):
        self._pages = pages
        return self
    
    def with_study_type(self, study_type: str):
        self._study_type = study_type
        return self
    
    def build(self) -> StudyModel:
        return StudyModel(
            name=self._name,
            study_id=self._study_id,
            centers=self._centers,
            datatypes=self._datatypes,
            pages=self._pages,
            mode=self._mode,
            study_type=self._study_type,
        )
```

```python
class PageProjectMetadataBuilder:
    """Builder for creating test PageProjectMetadata instances."""
    
    def __init__(self):
        self._study_id = "test-study"
        self._project_id = "test-project-id"
        self._project_label = "page-test"
        self._page_name = "test-page"
    
    def with_page_name(self, page_name: str):
        self._page_name = page_name
        return self
    
    def with_study_id(self, study_id: str):
        self._study_id = study_id
        return self
    
    def build(self) -> PageProjectMetadata:
        return PageProjectMetadata(
            study_id=self._study_id,
            project_id=self._project_id,
            project_label=self._project_label,
            page_name=self._page_name,
        )
```

### Mock Strategy

Centralize mock creation for Flywheel components:

```python
@pytest.fixture
def mock_flywheel_proxy():
    """Reusable Flywheel proxy mock with sensible defaults."""
    proxy = Mock(spec=FlywheelProxy)
    proxy.add_project.return_value = create_mock_project()
    return proxy

def create_mock_project(
    project_id: str = "test-id",
    label: str = "test-label",
    **kwargs
) -> Mock:
    """Factory for creating mock projects with defaults."""
    project = Mock(spec=ProjectAdaptor)
    project.id = project_id
    project.label = label
    for key, value in kwargs.items():
        setattr(project, key, value)
    return project

def create_mock_center(
    center_id: str = "center-01",
    is_active: bool = True,
    **kwargs
) -> Mock:
    """Factory for creating mock centers with defaults."""
    center = Mock(spec=CenterGroup)
    center.id = center_id
    center.is_active.return_value = is_active
    for key, value in kwargs.items():
        setattr(center, key, value)
    return center
```

### Testing Checklist

Before considering the feature complete:

- [ ] All unit tests pass
- [ ] All property tests pass (minimum 100 iterations each)
- [ ] Integration tests pass
- [ ] Error handling tests pass
- [ ] Edge case tests pass (empty pages, inactive centers, no pages)
- [ ] Manual testing with real Flywheel instance
- [ ] Visitor pattern tested with actual user management gear
- [ ] Documentation updated
- [ ] Code review completed
- [ ] Consistency with dashboard pattern verified
