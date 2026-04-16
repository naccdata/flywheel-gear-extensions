"""Tests for projects.study_mapping module.

NOTE: Some tests in this file are skipped because they test implementation details
that changed during the study-model-flexible-configuration refactoring. Specifically:
- Page creation was moved from StudyMapper.map_center_pipelines() to StudyMappingVisitor
- This was done to avoid duplication in mixed-mode studies where both mappers would
  create pages via super().map_center_pipelines()
- The functionality is still tested in test_study_mapping_mixed_mode.py and
  test_backward_compatible_project_structure.py which test through the visitor
"""

from unittest.mock import Mock

import pytest
from projects.study import StudyModel
from projects.study_mapping import AggregationMapper, DistributionMapper


class TestStudyMapperPageLabel:
    """Tests for StudyMapper.page_label() method."""

    def test_page_label_primary_study(self):
        """Test page_label() for primary study returns 'page-{page_name}'."""
        study = StudyModel(
            name="Primary Study",  # pyright: ignore[reportCallIssue]
            study_id="primary-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        assert mapper.page_label("enrollment") == "page-enrollment"
        assert mapper.page_label("data-entry") == "page-data-entry"
        assert mapper.page_label("qc-status") == "page-qc-status"

    def test_page_label_affiliated_study(self):
        """Test page_label() for affiliated study returns 'page-{page_name}-

        {study_id}'.
        """
        study = StudyModel(
            name="Affiliated Study",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="affiliated",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        assert mapper.page_label("enrollment") == "page-enrollment-nacc-ftld"
        assert mapper.page_label("data-entry") == "page-data-entry-nacc-ftld"
        assert mapper.page_label("qc-status") == "page-qc-status-nacc-ftld"

    def test_page_label_distribution_mapper(self):
        """Test page_label() works with DistributionMapper."""
        study = StudyModel(
            name="Distribution Study",  # pyright: ignore[reportCallIssue]
            study_id="dist-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="distribution",
            study_type="affiliated",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = DistributionMapper(study=study, proxy=mock_proxy)

        assert mapper.page_label("enrollment") == "page-enrollment-dist-study"


@pytest.mark.skip(
    reason=(
        "Page creation moved to StudyMappingVisitor - "
        "see test_study_mapping_mixed_mode.py"
    )
)
class TestStudyMapperAddPage:
    """Tests for StudyMapper.__add_page() method."""

    def test_add_page_creates_project_with_correct_label(self):
        """Test __add_page() creates project with correct label."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center with side_effect to return proper mocks
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify add_project was called with page label
        # Check that "page-enrollment" was in the calls
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]
        assert "page-enrollment" in call_args_list

    def test_add_page_stores_metadata(self):
        """Test __add_page() stores PageProjectMetadata in study_info."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata, PageProjectMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center and project
        mock_center = Mock()
        mock_project = Mock()
        mock_project.id = "project-123"
        mock_project.label = "page-enrollment"
        mock_center.add_project.return_value = mock_project
        mock_center.is_active.return_value = True

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines which calls __add_page
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify metadata was stored
        assert study_info.page_projects is not None
        assert "page-enrollment" in study_info.page_projects
        page_metadata = study_info.page_projects["page-enrollment"]
        assert isinstance(page_metadata, PageProjectMetadata)
        assert page_metadata.study_id == "test-study"
        assert page_metadata.project_id == "project-123"
        assert page_metadata.project_label == "page-enrollment"
        assert page_metadata.page_name == "enrollment"

    def test_add_page_handles_project_creation_failure(self):
        """Test __add_page() handles project creation failure gracefully."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center that fails to create project
        mock_center = Mock()
        mock_center.add_project.return_value = None  # Simulate failure
        mock_center.is_active.return_value = True
        mock_center.id = "center-01"

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call should not raise exception
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify metadata was not stored (project creation failed)
        assert study_info.page_projects == {} or study_info.page_projects is None

    def test_add_page_multiple_pages(self):
        """Test __add_page() handles multiple pages correctly."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry", "qc-status"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = lambda label: create_mock_project(label)

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify all three pages were created
        assert study_info.page_projects is not None
        assert len(study_info.page_projects) == 3
        assert "page-enrollment" in study_info.page_projects
        assert "page-data-entry" in study_info.page_projects
        assert "page-qc-status" in study_info.page_projects

        # Verify each has correct page_name
        assert study_info.page_projects["page-enrollment"].page_name == "enrollment"
        assert study_info.page_projects["page-data-entry"].page_name == "data-entry"
        assert study_info.page_projects["page-qc-status"].page_name == "qc-status"

    def test_add_page_affiliated_study(self):
        """Test __add_page() uses correct label for affiliated study."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="NACC FTLD",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="affiliated",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center with side_effect
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="nacc-ftld",
            study_name="NACC FTLD",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify correct label was used
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]
        assert "page-enrollment-nacc-ftld" in call_args_list
        assert study_info.page_projects is not None
        assert "page-enrollment-nacc-ftld" in study_info.page_projects

    def test_add_page_inactive_center(self):
        """Test __add_page() skips inactive centers."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock inactive center with proper mock projects
        mock_center = Mock()
        mock_center.is_active.return_value = False

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify page projects were not created (center is inactive)
        # Check that no page-* projects were created
        if mock_center.add_project.called:
            call_args_list = [
                call[0][0] for call in mock_center.add_project.call_args_list
            ]
            page_calls = [
                label for label in call_args_list if label.startswith("page-")
            ]
            assert len(page_calls) == 0, (
                "No page projects should be created for inactive centers"
            )

        # Verify no page projects in metadata
        assert study_info.page_projects == {} or study_info.page_projects is None


@pytest.mark.skip(
    reason=(
        "Page creation moved to StudyMappingVisitor - "
        "see test_study_mapping_mixed_mode.py"
    )
)
class TestMapCenterPipelinesWithPages:
    """Tests for StudyMapper.map_center_pipelines() with pages
    functionality."""

    def test_map_center_pipelines_creates_pages_for_study_with_pages(self):
        """Test map_center_pipelines() creates page projects when study has
        pages.

        Validates Requirements 2.1, 5.1, 5.5
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify page projects were created
        assert study_info.page_projects is not None
        assert len(study_info.page_projects) == 2
        assert "page-enrollment" in study_info.page_projects
        assert "page-data-entry" in study_info.page_projects

    def test_map_center_pipelines_no_pages_for_study_without_pages(self):
        """Test map_center_pipelines() creates no pages when study has no
        pages.

        Validates Requirements 2.5
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=None,  # No pages
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify no page projects were created
        if mock_center.add_project.called:
            call_args_list = [
                call[0][0] for call in mock_center.add_project.call_args_list
            ]
            page_calls = [
                label for label in call_args_list if label.startswith("page-")
            ]
            assert len(page_calls) == 0

        # Verify no page projects in metadata
        assert study_info.page_projects == {} or study_info.page_projects is None

    def test_map_center_pipelines_no_pages_for_empty_pages_list(self):
        """Test map_center_pipelines() creates no pages when pages list is
        empty.

        Validates Requirements 2.5
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=[],  # Empty pages list
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify no page projects were created
        if mock_center.add_project.called:
            call_args_list = [
                call[0][0] for call in mock_center.add_project.call_args_list
            ]
            page_calls = [
                label for label in call_args_list if label.startswith("page-")
            ]
            assert len(page_calls) == 0

        # Verify no page projects in metadata
        assert study_info.page_projects == {} or study_info.page_projects is None

    def test_map_center_pipelines_inactive_center_no_pages(self):
        """Test map_center_pipelines() skips page creation for inactive
        centers.

        Validates Requirements 2.4
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock inactive center
        mock_center = Mock()
        mock_center.is_active.return_value = False

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify no page projects were created
        if mock_center.add_project.called:
            call_args_list = [
                call[0][0] for call in mock_center.add_project.call_args_list
            ]
            page_calls = [
                label for label in call_args_list if label.startswith("page-")
            ]
            assert len(page_calls) == 0, (
                "No page projects should be created for inactive centers"
            )

        # Verify no page projects in metadata
        assert study_info.page_projects == {} or study_info.page_projects is None

    def test_map_center_pipelines_single_page(self):
        """Test map_center_pipelines() handles single page correctly.

        Validates Requirements 2.1, 5.1
        """
        from centers.center_group import CenterStudyMetadata, PageProjectMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True
        mock_project = Mock()
        mock_project.id = "project-123"
        mock_project.label = "page-enrollment"
        mock_center.add_project.return_value = mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify single page project was created
        assert study_info.page_projects is not None
        assert len(study_info.page_projects) == 1
        assert "page-enrollment" in study_info.page_projects
        page_metadata = study_info.page_projects["page-enrollment"]
        assert isinstance(page_metadata, PageProjectMetadata)
        assert page_metadata.page_name == "enrollment"

    def test_map_center_pipelines_multiple_pages(self):
        """Test map_center_pipelines() handles multiple pages correctly.

        Validates Requirements 2.1, 5.1, 5.2
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry", "qc-status"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify all three page projects were created
        assert study_info.page_projects is not None
        assert len(study_info.page_projects) == 3
        assert "page-enrollment" in study_info.page_projects
        assert "page-data-entry" in study_info.page_projects
        assert "page-qc-status" in study_info.page_projects

        # Verify each has correct page_name
        assert study_info.page_projects["page-enrollment"].page_name == "enrollment"
        assert study_info.page_projects["page-data-entry"].page_name == "data-entry"
        assert study_info.page_projects["page-qc-status"].page_name == "qc-status"

    def test_map_center_pipelines_affiliated_study_with_pages(self):
        """Test map_center_pipelines() uses correct labels for affiliated
        study.

        Validates Requirements 2.3, 5.1
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="NACC FTLD",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="affiliated",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        study_info = CenterStudyMetadata(
            study_id="nacc-ftld",
            study_name="NACC FTLD",
        )

        # Call map_center_pipelines
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify correct labels were used for affiliated study
        assert study_info.page_projects is not None
        assert "page-enrollment-nacc-ftld" in study_info.page_projects
        assert "page-data-entry-nacc-ftld" in study_info.page_projects
        assert (
            study_info.page_projects["page-enrollment-nacc-ftld"].page_name
            == "enrollment"
        )
        assert (
            study_info.page_projects["page-data-entry-nacc-ftld"].page_name
            == "data-entry"
        )

    def test_map_center_pipelines_active_center_with_pages(self):
        """Test map_center_pipelines() creates pages only for active centers.

        Validates Requirements 2.4, 5.5
        """
        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Test with active center
        active_center = Mock()
        active_center.is_active.return_value = True

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        active_center.add_project.side_effect = create_mock_project

        active_study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        mapper.map_center_pipelines(
            center=active_center, study_info=active_study_info, pipeline_adcid=1
        )

        # Verify page created for active center
        assert active_study_info.page_projects is not None
        assert len(active_study_info.page_projects) == 1

        # Test with inactive center
        inactive_center = Mock()
        inactive_center.is_active.return_value = False
        inactive_center.add_project.side_effect = create_mock_project

        inactive_study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        mapper.map_center_pipelines(
            center=inactive_center, study_info=inactive_study_info, pipeline_adcid=1
        )

        # Verify no pages created for inactive center
        assert (
            inactive_study_info.page_projects == {}
            or inactive_study_info.page_projects is None
        )


@pytest.mark.skip(
    reason=(
        "Page creation moved to StudyMappingVisitor - "
        "see test_study_mapping_mixed_mode.py"
    )
)
class TestPageProjectsIntegration:
    """Integration tests for page project creation end-to-end.

    These tests validate complete workflows from study configuration
    through project creation and metadata storage.
    """

    def test_end_to_end_page_project_creation(self):
        """Test complete workflow from study YAML to page project creation.

        Validates Requirements 2.1, 2.6, 3.1, 5.1, 5.5

        This test simulates the complete process:
        1. Study configuration with pages field
        2. Study mapping to center
        3. Page project creation in Flywheel
        4. Metadata storage in center metadata
        """
        from centers.center_group import CenterStudyMetadata

        # Create study with pages field (simulating YAML configuration)
        study = StudyModel(
            name="NACC UDS",  # pyright: ignore[reportCallIssue]
            study_id="nacc-uds",
            centers=[],
            datatypes=["clinical", "imaging"],
            pages=["enrollment", "data-entry", "qc-status"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )

        # Create mock Flywheel proxy
        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        # Track created projects
        created_projects = {}

        def create_mock_project(label):
            project = Mock()
            project.id = f"fw-project-{label}"
            project.label = label
            created_projects[label] = project
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Create study metadata
        study_info = CenterStudyMetadata(
            study_id="nacc-uds",
            study_name="NACC UDS",
        )

        # Execute study mapping (this is the main integration point)
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify all page projects were created (among other projects)
        assert "page-enrollment" in created_projects
        assert "page-data-entry" in created_projects
        assert "page-qc-status" in created_projects

        # Verify metadata was stored correctly (only page projects)
        assert study_info.page_projects is not None
        assert len(study_info.page_projects) == 3

        # Verify each page project has correct metadata
        enrollment_page = study_info.get_page("page-enrollment")
        assert enrollment_page is not None
        assert enrollment_page.study_id == "nacc-uds"
        assert enrollment_page.project_label == "page-enrollment"
        assert enrollment_page.page_name == "enrollment"
        assert enrollment_page.project_id == "fw-project-page-enrollment"

        data_entry_page = study_info.get_page("page-data-entry")
        assert data_entry_page is not None
        assert data_entry_page.study_id == "nacc-uds"
        assert data_entry_page.project_label == "page-data-entry"
        assert data_entry_page.page_name == "data-entry"
        assert data_entry_page.project_id == "fw-project-page-data-entry"

        qc_status_page = study_info.get_page("page-qc-status")
        assert qc_status_page is not None
        assert qc_status_page.study_id == "nacc-uds"
        assert qc_status_page.project_label == "page-qc-status"
        assert qc_status_page.page_name == "qc-status"
        assert qc_status_page.project_id == "fw-project-page-qc-status"

    def test_multi_study_integration(self):
        """Test page projects for both primary and affiliated studies.

        Validates Requirements 8.1, 8.2, 8.3, 8.4, 8.5

        This test verifies:
        1. Primary study creates pages without suffix
        2. Affiliated study creates pages with study_id suffix
        3. Both studies can coexist in same center
        4. No label conflicts between studies
        """
        from centers.center_group import CenterStudyMetadata

        # Create primary study with pages
        primary_study = StudyModel(
            name="NACC UDS",  # pyright: ignore[reportCallIssue]
            study_id="nacc-uds",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )

        # Create affiliated study with pages
        affiliated_study = StudyModel(
            name="NACC FTLD",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry"],
            mode="aggregation",
            study_type="affiliated",
            legacy=True,
        )

        # Create mock Flywheel proxy
        mock_proxy = Mock()

        # Create mappers for both studies
        primary_mapper = AggregationMapper(
            study=primary_study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )
        affiliated_mapper = AggregationMapper(
            study=affiliated_study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        # Track all created projects across both studies
        all_created_projects = {}

        def create_mock_project(label):
            project = Mock()
            project.id = f"fw-project-{label}"
            project.label = label
            all_created_projects[label] = project
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Create study metadata for primary study
        primary_study_info = CenterStudyMetadata(
            study_id="nacc-uds",
            study_name="NACC UDS",
        )

        # Map primary study
        primary_mapper.map_center_pipelines(
            center=mock_center, study_info=primary_study_info, pipeline_adcid=1
        )

        # Create study metadata for affiliated study
        affiliated_study_info = CenterStudyMetadata(
            study_id="nacc-ftld",
            study_name="NACC FTLD",
        )

        # Map affiliated study
        affiliated_mapper.map_center_pipelines(
            center=mock_center, study_info=affiliated_study_info, pipeline_adcid=2
        )

        # Verify primary study pages have no suffix
        assert "page-enrollment" in all_created_projects
        assert "page-data-entry" in all_created_projects

        # Verify affiliated study pages have study_id suffix
        assert "page-enrollment-nacc-ftld" in all_created_projects
        assert "page-data-entry-nacc-ftld" in all_created_projects

        # Verify no label conflicts between page projects (4 page projects total)
        page_projects = [k for k in all_created_projects if k.startswith("page-")]
        assert len(page_projects) == 4

        # Verify primary study metadata
        assert primary_study_info.page_projects is not None
        assert len(primary_study_info.page_projects) == 2
        primary_enrollment = primary_study_info.get_page("page-enrollment")
        assert primary_enrollment is not None
        assert primary_enrollment.project_label == "page-enrollment"
        assert primary_enrollment.page_name == "enrollment"

        # Verify affiliated study metadata
        assert affiliated_study_info.page_projects is not None
        assert len(affiliated_study_info.page_projects) == 2
        affiliated_enrollment = affiliated_study_info.get_page(
            "page-enrollment-nacc-ftld"
        )
        assert affiliated_enrollment is not None
        assert affiliated_enrollment.project_label == "page-enrollment-nacc-ftld"
        assert affiliated_enrollment.page_name == "enrollment"

        # Verify labels are unique across both studies
        primary_labels = set(primary_study_info.page_projects.keys())
        affiliated_labels = set(affiliated_study_info.page_projects.keys())
        assert len(primary_labels.intersection(affiliated_labels)) == 0

    def test_error_recovery_integration(self):
        """Test error handling and recovery during page project creation.

        Validates Requirements 5.4

        This test verifies:
        1. Errors during project creation are logged with context
        2. Partial success (other pages still created)
        3. System remains in consistent state after errors
        """
        import contextlib

        from centers.center_group import CenterStudyMetadata

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=["clinical"],
            pages=["enrollment", "data-entry", "qc-status"],
            mode="aggregation",
            study_type="primary",
            legacy=True,
        )

        mock_proxy = Mock()
        mapper = AggregationMapper(
            study=study, pipelines=[], proxy=mock_proxy, admin_access=[]
        )

        # Create mock center
        mock_center = Mock()
        mock_center.is_active.return_value = True

        # Track created projects and failures
        created_projects = {}
        failed_projects = []

        def create_mock_project_with_failure(label):
            # Simulate failure for data-entry page
            if label == "page-data-entry":
                failed_projects.append(label)
                raise Exception(f"Flywheel API error: Failed to create {label}")

            project = Mock()
            project.id = f"fw-project-{label}"
            project.label = label
            created_projects[label] = project
            return project

        mock_center.add_project.side_effect = create_mock_project_with_failure

        study_info = CenterStudyMetadata(
            study_id="test-study",
            study_name="Test Study",
        )

        # Execute study mapping - should handle error gracefully
        with contextlib.suppress(Exception):
            # Error is expected for data-entry page
            mapper.map_center_pipelines(
                center=mock_center, study_info=study_info, pipeline_adcid=1
            )

        # Verify partial success: enrollment and qc-status created
        # Note: The actual behavior depends on implementation
        # This test documents expected error handling behavior

        # Verify that at least some projects were attempted
        # Note: The error occurs during page creation, so other projects
        # (accepted, retrospective) may be created first
        assert mock_center.add_project.call_count >= 2

        # Verify the failure was for the expected project
        assert len(failed_projects) == 1
        assert "page-data-entry" in failed_projects

        # Verify system state remains consistent
        # (metadata should only contain successfully created projects)
        if study_info.page_projects:
            # If any projects were created, verify they don't include failed one
            assert "page-data-entry" not in study_info.page_projects


class TestMapperDatatypeFiltering:
    """Tests for mapper datatype filtering functionality."""

    def test_aggregation_mapper_with_subset_of_datatypes(self):
        """Test AggregationMapper processes only specified datatypes."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        # Create study with multiple aggregation datatypes
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=[
                {"name": "form", "mode": "aggregation"},
                {"name": "dicom", "mode": "aggregation"},
                {"name": "csv", "mode": "aggregation"},
            ],
            mode=None,
            study_type="primary",
            legacy=False,
        )

        mock_proxy = Mock()
        mock_center = Mock()
        mock_center.is_active.return_value = True
        mock_center.add_project.return_value = Mock(id="proj-1", label="test-label")

        study_info = CenterStudyMetadata(study_id="test-study", study_name="Test Study")

        mapper = AggregationMapper(
            study=study, pipelines=["ingest"], proxy=mock_proxy, admin_access=[]
        )

        # Call with subset of datatypes
        mapper.map_center_pipelines(
            center=mock_center,
            study_info=study_info,
            pipeline_adcid=1,
            datatypes=["form", "dicom"],
        )

        # Verify only specified datatypes were processed
        # Should create: accepted + 2 ingest projects (form, dicom)
        assert mock_center.add_project.call_count == 3

        # Check that the correct project labels were created
        project_labels = [
            call_args[0][0] for call_args in mock_center.add_project.call_args_list
        ]
        assert "accepted" in project_labels
        assert "ingest-form" in project_labels
        assert "ingest-dicom" in project_labels
        assert "ingest-csv" not in project_labels

    def test_aggregation_mapper_defaults_to_all_aggregation_datatypes(self):
        """Test AggregationMapper defaults to all aggregation datatypes when.

        none specified.
        """
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        # Create study with mixed mode datatypes (affiliated study allows mixed modes)
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=[
                {"name": "form", "mode": "aggregation"},
                {"name": "dicom", "mode": "aggregation"},
                {"name": "csv", "mode": "distribution"},
            ],
            mode=None,
            study_type="affiliated",
            legacy=False,
        )

        mock_proxy = Mock()
        mock_center = Mock()
        mock_center.is_active.return_value = True
        mock_center.add_project.return_value = Mock(id="proj-1", label="test-label")

        study_info = CenterStudyMetadata(study_id="test-study", study_name="Test Study")

        mapper = AggregationMapper(
            study=study, pipelines=["ingest"], proxy=mock_proxy, admin_access=[]
        )

        # Call without specifying datatypes
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify only aggregation datatypes were processed
        # Should create: accepted + 2 ingest projects (form, dicom)
        assert mock_center.add_project.call_count == 3

        project_labels = [
            call_args[0][0] for call_args in mock_center.add_project.call_args_list
        ]
        assert "accepted-test-study" in project_labels
        assert "ingest-form-test-study" in project_labels
        assert "ingest-dicom-test-study" in project_labels
        assert "ingest-csv-test-study" not in project_labels

    def test_distribution_mapper_with_subset_of_datatypes(self):
        """Test DistributionMapper processes only specified datatypes."""
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        # Create study with multiple distribution datatypes
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=[
                {"name": "form", "mode": "distribution"},
                {"name": "dicom", "mode": "distribution"},
                {"name": "csv", "mode": "distribution"},
            ],
            mode=None,
            study_type="affiliated",
            legacy=False,
        )

        mock_proxy = Mock()
        mock_center = Mock()
        mock_center.is_active.return_value = True
        mock_center.add_project.return_value = Mock(id="proj-1", label="test-label")

        study_info = CenterStudyMetadata(study_id="test-study", study_name="Test Study")

        mapper = DistributionMapper(study=study, proxy=mock_proxy)

        # Call with subset of datatypes
        mapper.map_center_pipelines(
            center=mock_center,
            study_info=study_info,
            pipeline_adcid=1,
            datatypes=["form", "dicom"],
        )

        # Verify only specified datatypes were processed
        # Should create 2 distribution projects (form, dicom)
        assert mock_center.add_project.call_count == 2

        project_labels = [
            call_args[0][0] for call_args in mock_center.add_project.call_args_list
        ]
        assert "distribution-form-test-study" in project_labels
        assert "distribution-dicom-test-study" in project_labels
        assert "distribution-csv-test-study" not in project_labels

    def test_distribution_mapper_defaults_to_all_distribution_datatypes(self):
        """Test DistributionMapper defaults to all distribution datatypes when.

        none specified.
        """
        from unittest.mock import Mock

        from centers.center_group import CenterStudyMetadata

        # Create study with mixed mode datatypes
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[],
            datatypes=[
                {"name": "form", "mode": "distribution"},
                {"name": "dicom", "mode": "distribution"},
                {"name": "csv", "mode": "aggregation"},
            ],
            mode=None,
            study_type="affiliated",
            legacy=False,
        )

        mock_proxy = Mock()
        mock_center = Mock()
        mock_center.is_active.return_value = True
        mock_center.add_project.return_value = Mock(id="proj-1", label="test-label")

        study_info = CenterStudyMetadata(study_id="test-study", study_name="Test Study")

        mapper = DistributionMapper(study=study, proxy=mock_proxy)

        # Call without specifying datatypes
        mapper.map_center_pipelines(
            center=mock_center, study_info=study_info, pipeline_adcid=1
        )

        # Verify only distribution datatypes were processed
        # Should create 2 distribution projects (form, dicom)
        assert mock_center.add_project.call_count == 2

        project_labels = [
            call_args[0][0] for call_args in mock_center.add_project.call_args_list
        ]
        assert "distribution-form-test-study" in project_labels
        assert "distribution-dicom-test-study" in project_labels
        assert "distribution-csv-test-study" not in project_labels
