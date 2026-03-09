"""Property-based tests for page project creation.

This module contains property tests that validate universal correctness
properties of the page project creation feature across all valid inputs.

Feature: study-page-resources
"""

from unittest.mock import Mock

from centers.center_group import CenterStudyMetadata
from hypothesis import given, settings
from hypothesis import strategies as st
from projects.study import StudyCenterModel, StudyModel
from projects.study_mapping import AggregationMapper

# Hypothesis strategies for generating test data


@st.composite
def study_with_pages_strategy(draw, study_type=None):
    """Generate StudyModel with pages field.

    Args:
        draw: Hypothesis draw function
        study_type: If provided, use this study type; otherwise randomly choose

    Returns:
        A randomly generated StudyModel with pages
    """
    # Generate 1-5 unique page names (no duplicates)
    num_pages = draw(st.integers(min_value=1, max_value=5))
    pages = draw(
        st.lists(
            st.text(
                min_size=2,  # Minimum 2 chars to avoid single-char collisions
                max_size=20,
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
                ),
            ).filter(lambda x: x and not x.startswith("-") and not x.endswith("-")),
            min_size=num_pages,
            max_size=num_pages,
            unique=True,  # Ensure no duplicate page names
        )
    )

    # Generate study_id that doesn't match any page name
    study_id = draw(
        st.text(
            min_size=2,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), whitelist_characters="-"
            ),
        ).filter(
            lambda x: x
            and not x.startswith("-")
            and not x.endswith("-")
            and x not in pages  # Ensure study_id doesn't match any page name
        )
    )

    # Choose study type
    chosen_study_type = (
        study_type
        if study_type is not None
        else draw(st.sampled_from(["primary", "affiliated"]))
    )

    return StudyModel(
        name=f"Test Study {study_id}",  # pyright: ignore[reportCallIssue]
        study_id=study_id,
        centers=[StudyCenterModel(center_id="center-01")],
        datatypes=["clinical"],
        pages=pages,
        mode="aggregation",
        study_type=chosen_study_type,
        legacy=True,
        published=False,
    )


@st.composite
def active_centers_strategy(draw, min_centers=1, max_centers=5):
    """Generate list of mock active centers.

    Args:
        draw: Hypothesis draw function
        min_centers: Minimum number of centers
        max_centers: Maximum number of centers

    Returns:
        List of mock CenterGroup instances
    """
    num_centers = draw(st.integers(min_value=min_centers, max_value=max_centers))
    centers = []

    for i in range(num_centers):
        center = Mock()
        center.id = f"center-{i:02d}"
        center.is_active.return_value = True

        # Mock add_project to return a project with the given label
        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        center.add_project.side_effect = create_mock_project
        centers.append(center)

    return centers


# Property Tests


@settings(max_examples=100)
@given(
    study=study_with_pages_strategy(),
    centers=active_centers_strategy(min_centers=1, max_centers=5),
)
def test_property_page_projects_created_for_all_pages(study, centers):
    """Property 3: Page Projects Created for All Pages.

    For any study with N page names and M active centers, the system should
    create exactly N * M page stub projects after study mapping completes.

    Validates Requirements 2.1, 7.1, 7.4

    Feature: study-page-resources, Property 3: Page Projects Created for All Pages
    """
    # Arrange
    mock_proxy = Mock()
    mapper = AggregationMapper(
        study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
    )

    # Act - map study to all centers
    study_infos = []
    for center in centers:
        study_info = CenterStudyMetadata(
            study_id=study.study_id,
            study_name=study.name,
        )
        mapper.map_center_pipelines(
            center=center, study_info=study_info, pipeline_adcid=1
        )
        study_infos.append(study_info)

    # Assert - verify N * M projects created
    n_pages = len(study.pages) if study.pages else 0
    m_centers = len(centers)
    expected_total_projects = n_pages * m_centers

    # Count total page projects across all centers
    total_page_projects = sum(
        len(info.page_projects) if info.page_projects else 0 for info in study_infos
    )

    assert total_page_projects == expected_total_projects, (
        f"Expected {expected_total_projects} page projects "
        f"({n_pages} pages * {m_centers} centers), "
        f"but got {total_page_projects}"
    )

    # Verify each center has exactly N page projects
    for study_info in study_infos:
        assert study_info.page_projects is not None
        assert len(study_info.page_projects) == n_pages, (
            f"Each center should have {n_pages} page projects, "
            f"but got {len(study_info.page_projects)}"
        )


@settings(max_examples=100)
@given(study=study_with_pages_strategy(study_type="primary"))
def test_property_primary_study_label_format(study):
    """Property 4: Primary Study Label Format.

    For any primary study and any page name, the generated project label
    should match the format "page-{page_name}" exactly.

    Validates Requirements 2.2, 8.1, 8.4

    Feature: study-page-resources, Property 4: Primary Study Label Format
    """
    # Arrange
    mock_proxy = Mock()
    mapper = AggregationMapper(
        study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
    )

    # Act & Assert - verify label format for each page
    assert study.pages is not None
    for page_name in study.pages:
        label = mapper.page_label(page_name)

        # Verify format matches exactly
        expected_label = f"page-{page_name}"
        assert label == expected_label, (
            f"Primary study page label should be 'page-{page_name}', but got '{label}'"
        )

        # Verify no study_id suffix
        assert not label.endswith(f"-{study.study_id}"), (
            f"Primary study label should not have study_id suffix, but got '{label}'"
        )


@settings(max_examples=100)
@given(study=study_with_pages_strategy(study_type="affiliated"))
def test_property_affiliated_study_label_format(study):
    """Property 5: Affiliated Study Label Format.

    For any affiliated study with study_id and any page name, the generated
    project label should match the format "page-{page_name}-{study_id}" exactly.

    Validates Requirements 2.3, 8.2, 8.5

    Feature: study-page-resources, Property 5: Affiliated Study Label Format
    """
    # Arrange
    mock_proxy = Mock()
    mapper = AggregationMapper(
        study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
    )

    # Act & Assert - verify label format for each page
    assert study.pages is not None
    for page_name in study.pages:
        label = mapper.page_label(page_name)

        # Verify format matches exactly
        expected_label = f"page-{page_name}-{study.study_id}"
        assert label == expected_label, (
            f"Affiliated study page label should be "
            f"'page-{page_name}-{study.study_id}', but got '{label}'"
        )

        # Verify study_id suffix is present
        assert label.endswith(f"-{study.study_id}"), (
            f"Affiliated study label should have study_id suffix, but got '{label}'"
        )

        # Verify page name is in the label
        assert page_name in label, (
            f"Page name '{page_name}' should be in label, but got '{label}'"
        )
