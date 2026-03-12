"""Tests for mixed-mode study mapping functionality.

This module tests the StudyMappingVisitor's ability to handle studies
with mixed datatypes (some aggregation, some distribution) and per-
dashboard level configuration.
"""

from unittest.mock import Mock, patch

from projects.study import DatatypeConfig, StudyModel
from projects.study_mapping import StudyMappingVisitor


class TestMixedModeStudyMapping:
    """Tests for StudyMappingVisitor with mixed-mode studies."""

    def test_study_with_only_aggregation_datatypes(self, mock_flywheel_proxy):
        """Test study with only aggregation datatypes creates only aggregation
        projects.

        Validates Requirements 10.1, 10.2, 10.4
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
                DatatypeConfig(name="dicom", mode="aggregation"),
            ],
            study_type="primary",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor
        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify aggregation projects were created
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        # Should have accepted project
        assert "accepted" in call_args_list

        # Should have ingest and sandbox projects for each datatype
        assert "ingest-form" in call_args_list
        assert "sandbox-form" in call_args_list
        assert "ingest-dicom" in call_args_list
        assert "sandbox-dicom" in call_args_list

        # Should NOT have distribution projects
        assert "distribution-form" not in call_args_list
        assert "distribution-dicom" not in call_args_list

    def test_study_with_only_distribution_datatypes(self, mock_flywheel_proxy):
        """Test study with only distribution datatypes creates only
        distribution projects.

        Validates Requirements 10.2, 10.5
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[
                DatatypeConfig(name="form", mode="distribution"),
                DatatypeConfig(name="csv", mode="distribution"),
            ],
            study_type="affiliated",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor and StudyGroup.create
        with (
            patch(
                "projects.study_mapping.CenterGroup.create_from_group_adaptor",
                return_value=mock_center,
            ),
            patch("projects.study_mapping.StudyGroup.create"),
        ):
            visitor.visit_study(study)

        # Verify distribution projects were created
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        # Should have distribution projects for each datatype
        assert "distribution-form-test-study" in call_args_list
        assert "distribution-csv-test-study" in call_args_list

        # Should NOT have aggregation projects
        assert "accepted-test-study" not in call_args_list
        assert "ingest-form-test-study" not in call_args_list
        assert "sandbox-form-test-study" not in call_args_list

    def test_study_with_mixed_modes(self, mock_flywheel_proxy):
        """Test study with mixed modes creates both aggregation and
        distribution projects.

        Validates Requirements 5.3, 10.1, 10.2, 10.3
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=[
                {
                    "center-id": "center-01",
                    "enrollment-pattern": "separate",
                    "pipeline-adcid": 1,
                }
            ],
            datatypes=[
                DatatypeConfig(name="form", mode="aggregation"),
                DatatypeConfig(name="dicom", mode="aggregation"),
                DatatypeConfig(name="csv", mode="distribution"),
            ],
            study_type="affiliated",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor and StudyGroup.create
        with (
            patch(
                "projects.study_mapping.CenterGroup.create_from_group_adaptor",
                return_value=mock_center,
            ),
            patch("projects.study_mapping.StudyGroup.create"),
        ):
            visitor.visit_study(study)

        # Verify both aggregation and distribution projects were created
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        # Should have accepted project (aggregation)
        assert "accepted-test-study" in call_args_list

        # Should have aggregation projects for form and dicom
        assert "ingest-form-test-study" in call_args_list
        assert "sandbox-form-test-study" in call_args_list
        assert "ingest-dicom-test-study" in call_args_list
        assert "sandbox-dicom-test-study" in call_args_list

        # Should have distribution project for csv
        assert "distribution-csv-test-study" in call_args_list

        # Should NOT have distribution projects for aggregation datatypes
        assert "distribution-form-test-study" not in call_args_list
        assert "distribution-dicom-test-study" not in call_args_list

        # Should NOT have aggregation projects for distribution datatypes
        assert "ingest-csv-test-study" not in call_args_list
        assert "sandbox-csv-test-study" not in call_args_list


class TestDashboardLevelHandling:
    """Tests for dashboard creation at different levels."""

    def test_dashboard_creation_at_center_level(self, mock_flywheel_proxy):
        """Test dashboards with level 'center' are created in center groups.

        Validates Requirements 2.4, 6.1
        """
        from projects.study import DashboardConfig

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[DatatypeConfig(name="form", mode="aggregation")],
            dashboards=[
                DashboardConfig(name="dashboard-a", level="center"),
                DashboardConfig(name="dashboard-b", level="center"),
            ],
            study_type="primary",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor
        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify center-level dashboards were created
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        assert "dashboard-dashboard-a" in call_args_list
        assert "dashboard-dashboard-b" in call_args_list

    def test_study_level_dashboards_are_skipped(self, mock_flywheel_proxy, caplog):
        """Test dashboards with level 'study' are logged and skipped.

        Validates Requirements 2.5, 6.2
        """
        import logging

        from projects.study import DashboardConfig

        # Set log level to capture INFO messages
        caplog.set_level(logging.INFO)

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[DatatypeConfig(name="form", mode="aggregation")],
            dashboards=[
                DashboardConfig(name="dashboard-a", level="center"),
                DashboardConfig(name="dashboard-b", level="study"),
            ],
            study_type="primary",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor
        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify center-level dashboard was created
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]
        assert "dashboard-dashboard-a" in call_args_list

        # Verify study-level dashboard was NOT created
        assert "dashboard-dashboard-b" not in call_args_list

        # Verify log message about skipping study-level dashboards
        assert any(
            "Skipping study-level dashboards" in record.message
            for record in caplog.records
        )

    def test_mixed_dashboard_levels(self, mock_flywheel_proxy):
        """Test study with dashboards at different levels.

        Validates Requirements 6.3, 6.4
        """
        from projects.study import DashboardConfig

        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[DatatypeConfig(name="form", mode="aggregation")],
            dashboards=[
                DashboardConfig(name="dashboard-a", level="center"),
                DashboardConfig(name="dashboard-b", level="study"),
                DashboardConfig(name="dashboard-c", level="center"),
            ],
            study_type="primary",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor
        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify only center-level dashboards were created
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        assert "dashboard-dashboard-a" in call_args_list
        assert "dashboard-dashboard-c" in call_args_list
        assert "dashboard-dashboard-b" not in call_args_list

    def test_backward_compatible_dashboard_format(self, mock_flywheel_proxy):
        """Test old dashboard format (list of strings) defaults to center
        level.

        Validates Requirements 6.3
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=[DatatypeConfig(name="form", mode="aggregation")],
            dashboards=["dashboard-a", "dashboard-b"],  # Old format
            study_type="primary",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor
        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify dashboards were created at center level (default)
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        assert "dashboard-dashboard-a" in call_args_list
        assert "dashboard-dashboard-b" in call_args_list


class TestBackwardCompatibility:
    """Tests for backward compatibility with single-mode studies."""

    def test_single_mode_aggregation_compatibility(self, mock_flywheel_proxy):
        """Test study with old mode field produces same project structure.

        Validates Requirements 4.1, 4.2, 5.1, 5.2, 10.4
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=["form", "dicom"],  # Old format
            mode="aggregation",  # Old format
            study_type="primary",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor
        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify same project structure as before refactoring
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        # Should have accepted project
        assert "accepted" in call_args_list

        # Should have ingest and sandbox projects for each datatype
        assert "ingest-form" in call_args_list
        assert "sandbox-form" in call_args_list
        assert "ingest-dicom" in call_args_list
        assert "sandbox-dicom" in call_args_list

    def test_single_mode_distribution_compatibility(self, mock_flywheel_proxy):
        """Test distribution study with old mode field produces same project
        structure.

        Validates Requirements 5.1, 5.2, 10.5
        """
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test-study",
            centers=["center-01"],
            datatypes=["form", "csv"],  # Old format
            mode="distribution",  # Old format
            study_type="affiliated",
            legacy=True,
        )

        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Create mock group adaptor
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_flywheel_proxy.find_group.return_value = mock_group

        # Create mock center
        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        def create_mock_project(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            return project

        mock_center.add_project.side_effect = create_mock_project

        # Mock CenterGroup.create_from_group_adaptor and StudyGroup.create
        with (
            patch(
                "projects.study_mapping.CenterGroup.create_from_group_adaptor",
                return_value=mock_center,
            ),
            patch("projects.study_mapping.StudyGroup.create"),
        ):
            visitor.visit_study(study)

        # Verify same project structure as before refactoring
        call_args_list = [call[0][0] for call in mock_center.add_project.call_args_list]

        # Should have distribution projects for each datatype
        assert "distribution-form-test-study" in call_args_list
        assert "distribution-csv-test-study" in call_args_list
