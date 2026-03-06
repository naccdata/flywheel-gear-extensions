"""Property tests for page project metadata operations.

**Feature: study-page-resources**
"""

from centers.center_group import CenterStudyMetadata, PageProjectMetadata
from hypothesis import given, settings
from hypothesis import strategies as st


@st.composite
def page_project_metadata_strategy(draw):
    """Generate random PageProjectMetadata for testing."""
    study_id = draw(
        st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz-")
    )
    project_id = draw(st.text(min_size=8, max_size=16, alphabet="0123456789abcdef"))
    page_name = draw(
        st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz-")
    )
    project_label = f"page-{page_name}"

    return PageProjectMetadata(
        study_id=study_id,
        project_id=project_id,
        project_label=project_label,
        page_name=page_name,
    )


@given(page_metadata=page_project_metadata_strategy())
@settings(max_examples=100)
def test_metadata_storage_and_retrieval(page_metadata):
    """Property test: Metadata storage and retrieval round-trip.

    **Feature: study-page-resources, Property 8: Metadata Storage and Retrieval**
    **Validates: Requirements 3.1, 3.6, 3.7, 7.3**

    For any PageProjectMetadata instance, storing it and then retrieving it by
    project label should return the same metadata.
    """
    # Arrange - Create a study metadata object
    study = CenterStudyMetadata(
        study_id="test-study",
        study_name="Test Study",
    )

    # Act - Store the page metadata
    study.add_page(page_metadata)

    # Assert - Retrieve should return the same metadata
    retrieved = study.get_page(page_metadata.project_label)

    assert retrieved is not None, "Retrieved metadata should not be None"
    assert retrieved == page_metadata, "Retrieved metadata should match original"
    assert retrieved.study_id == page_metadata.study_id
    assert retrieved.project_id == page_metadata.project_id
    assert retrieved.project_label == page_metadata.project_label
    assert retrieved.page_name == page_metadata.page_name


@given(
    page_metadatas=st.lists(
        page_project_metadata_strategy(),
        min_size=2,
        max_size=10,
        unique_by=lambda x: x.project_label,
    )
)
@settings(max_examples=100)
def test_multiple_pages_storage(page_metadatas):
    """Property test: Multiple page projects stored correctly.

    **Feature: study-page-resources, Property 14: Multiple Page Projects Stored**
    **Validates: Requirements 7.2**

    For any study with multiple page names, all page projects should be stored
    in the CenterStudyMetadata.page_projects dictionary, each keyed by its
    unique project label.
    """
    # Arrange - Create a study metadata object
    study = CenterStudyMetadata(
        study_id="test-study",
        study_name="Test Study",
    )

    # Act - Store all page metadata objects
    for page_metadata in page_metadatas:
        study.add_page(page_metadata)

    # Assert - All pages should be stored
    assert study.page_projects is not None, "page_projects should not be None"
    assert len(study.page_projects) == len(page_metadatas), (
        f"Should have {len(page_metadatas)} pages stored"
    )

    # Assert - Each page should be retrievable by its label
    for page_metadata in page_metadatas:
        retrieved = study.get_page(page_metadata.project_label)
        assert retrieved is not None, (
            f"Page {page_metadata.project_label} should be retrievable"
        )
        assert retrieved == page_metadata, (
            f"Retrieved page should match original for {page_metadata.project_label}"
        )

    # Assert - All labels should be unique (keys in dictionary)
    labels = list(study.page_projects.keys())
    assert len(labels) == len(set(labels)), "All project labels should be unique"

    # Assert - Each label should match the format
    for label in labels:
        assert label.startswith("page-"), f"Label {label} should start with 'page-'"
