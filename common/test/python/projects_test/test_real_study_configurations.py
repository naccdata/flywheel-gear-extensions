"""Unit tests with real NACC study configurations.

This module tests the StudyModel and project management with actual
NACC study configurations to ensure backward compatibility and correct
project structure creation.

Validates Requirements 7.1, 7.3, 7.4
"""

from unittest.mock import Mock, patch

from projects.study import DatatypeConfig, StudyModel
from projects.study_mapping import StudyMappingVisitor


class TestRealNACCStudyConfigurations:
    """Tests using real NACC study configurations."""

    def test_nacc_uds_primary_study_old_format(self, mock_flywheel_proxy):
        """Test NACC UDS primary study with old configuration format.

        This test uses a realistic NACC UDS configuration with:
        - Old format: study-level mode field
        - Old format: datatypes as list of strings
        - Primary study type
        - Multiple datatypes (clinical, imaging)
        - Legacy data

        Validates Requirements 7.1, 7.3, 7.4
        """
        # Create NACC UDS study with old format
        study = StudyModel(
            name="NACC UDS",  # pyright: ignore[reportCallIssue]
            study_id="nacc-uds",
            centers=[
                {
                    "center-id": "center-01",
                    "enrollment-pattern": "co-enrollment",
                    "pipeline-adcid": 1,
                }
            ],
            datatypes=["clinical", "imaging"],  # Old format
            mode="aggregation",  # Old format
            study_type="primary",
            legacy=True,
            published=True,
        )

        # Verify study was created successfully
        assert study.name == "NACC UDS"
        assert study.study_id == "nacc-uds"
        assert study.study_type == "primary"
        assert study.legacy is True
        assert study.published is True

        # Verify old format was migrated to new format
        datatype_configs = study.get_datatype_configs()
        assert len(datatype_configs) == 2
        assert all(config.mode == "aggregation" for config in datatype_configs)

        # Verify primary study validation is maintained
        assert study.is_primary()

        # Create visitor and verify project structure
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Setup mocks
        mock_group = Mock()
        mock_group.id = "center-01"
        mock_group.label = "Center 01"
        mock_group.tags = []  # Add tags attribute
        mock_flywheel_proxy.find_group.return_value = mock_group

        mock_center = Mock()
        mock_center.id = "center-01"
        mock_center.adcid = 1
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        created_projects = []

        def track_project_creation(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            created_projects.append(label)
            return project

        mock_center.add_project.side_effect = track_project_creation

        # Mock release group for published studies
        mock_release_group = Mock()
        mock_release_group.tags = []
        mock_release_group.permissions = []  # Add permissions attribute
        mock_flywheel_proxy.get_group.return_value = mock_release_group

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify expected project structure for primary aggregation study
        # Primary studies have no suffix
        assert "accepted" in created_projects
        assert "ingest-clinical" in created_projects
        assert "sandbox-clinical" in created_projects
        assert "ingest-imaging" in created_projects
        assert "sandbox-imaging" in created_projects

        # Legacy study should have retrospective projects
        assert "retrospective-clinical" in created_projects
        assert "retrospective-imaging" in created_projects

    def test_nacc_ftld_affiliated_study_old_format(self, mock_flywheel_proxy):
        """Test NACC FTLD affiliated study with old configuration format.

        This test uses a realistic NACC FTLD configuration with:
        - Old format: study-level mode field
        - Old format: datatypes as list of strings
        - Affiliated study type
        - Single datatype (clinical)
        - Legacy data

        Validates Requirements 7.1, 7.3, 7.4
        """
        # Create NACC FTLD study with old format
        study = StudyModel(
            name="NACC FTLD",  # pyright: ignore[reportCallIssue]
            study_id="nacc-ftld",
            centers=[
                {
                    "center-id": "center-02",
                    "enrollment-pattern": "separate",
                    "pipeline-adcid": 2,
                }
            ],
            datatypes=["clinical"],  # Old format
            mode="aggregation",  # Old format
            study_type="affiliated",
            legacy=True,
            published=False,
        )

        # Verify study was created successfully
        assert study.name == "NACC FTLD"
        assert study.study_id == "nacc-ftld"
        assert study.study_type == "affiliated"
        assert study.legacy is True
        assert study.published is False

        # Verify old format was migrated to new format
        datatype_configs = study.get_datatype_configs()
        assert len(datatype_configs) == 1
        assert datatype_configs[0].mode == "aggregation"
        assert datatype_configs[0].name == "clinical"

        # Create visitor and verify project structure
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Setup mocks
        mock_group = Mock()
        mock_group.id = "center-02"
        mock_group.label = "Center 02"
        mock_flywheel_proxy.find_group.return_value = mock_group

        mock_center = Mock()
        mock_center.id = "center-02"
        mock_center.adcid = 2
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        created_projects = []

        def track_project_creation(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            created_projects.append(label)
            return project

        mock_center.add_project.side_effect = track_project_creation

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify expected project structure for affiliated aggregation study
        # Affiliated studies have suffix "-{study_id}"
        assert "accepted-nacc-ftld" in created_projects
        assert "ingest-clinical-nacc-ftld" in created_projects
        assert "sandbox-clinical-nacc-ftld" in created_projects

        # Legacy study should have retrospective project
        assert "retrospective-clinical-nacc-ftld" in created_projects

    def test_distribution_study_old_format(self, mock_flywheel_proxy):
        """Test distribution study with old configuration format.

        This test uses a distribution study configuration with:
        - Old format: study-level mode field
        - Old format: datatypes as list of strings
        - Affiliated study type (distribution requires affiliated)
        - Multiple datatypes
        - Non-legacy data

        Validates Requirements 7.1, 7.4
        """
        # Create distribution study with old format
        study = StudyModel(
            name="Distribution Study",  # pyright: ignore[reportCallIssue]
            study_id="dist-study",
            centers=["center-03"],
            datatypes=["form", "csv"],  # Old format
            mode="distribution",  # Old format
            study_type="affiliated",
            legacy=False,
            published=False,
        )

        # Verify study was created successfully
        assert study.name == "Distribution Study"
        assert study.study_id == "dist-study"
        assert study.study_type == "affiliated"
        assert study.legacy is False

        # Verify old format was migrated to new format
        datatype_configs = study.get_datatype_configs()
        assert len(datatype_configs) == 2
        assert all(config.mode == "distribution" for config in datatype_configs)

        # Create visitor and verify project structure
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Setup mocks
        mock_group = Mock()
        mock_group.id = "center-03"
        mock_group.label = "Center 03"
        mock_flywheel_proxy.find_group.return_value = mock_group

        mock_center = Mock()
        mock_center.id = "center-03"
        mock_center.adcid = 3
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        created_projects = []

        def track_project_creation(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            created_projects.append(label)
            return project

        mock_center.add_project.side_effect = track_project_creation

        with (
            patch(
                "projects.study_mapping.CenterGroup.create_from_group_adaptor",
                return_value=mock_center,
            ),
            patch("projects.study_mapping.StudyGroup.create"),
        ):
            visitor.visit_study(study)

        # Verify expected project structure for distribution study
        assert "distribution-form-dist-study" in created_projects
        assert "distribution-csv-dist-study" in created_projects

        # Should NOT have aggregation projects
        assert "accepted-dist-study" not in created_projects
        assert "ingest-form-dist-study" not in created_projects
        assert "sandbox-form-dist-study" not in created_projects

    def test_primary_study_allows_distribution(self):
        """Test that primary studies now allow distribution mode datatypes.

        Primary studies support mixed-mode datatypes (both aggregation
        and distribution).
        """
        # Primary study with distribution mode should now succeed
        study = StudyModel(
            name="Primary With Distribution",  # pyright: ignore[reportCallIssue]
            study_id="primary-dist",
            centers=["center-01"],
            datatypes=["form"],
            mode="distribution",
            study_type="primary",
            legacy=False,
        )

        assert study.study_type == "primary"
        assert study.get_datatypes_by_mode("distribution") == ["form"]

    def test_new_format_with_mixed_modes(self, mock_flywheel_proxy):
        """Test new format configuration with mixed modes.

        This test uses the new configuration format with:
        - New format: datatype-level mode configuration
        - Mixed modes: some aggregation, some distribution
        - Affiliated study type
        - Multiple datatypes

        Validates Requirements 7.1, 7.4
        """
        # Create study with new format
        study = StudyModel(
            name="Mixed Mode Study",  # pyright: ignore[reportCallIssue]
            study_id="mixed-study",
            centers=[
                {
                    "center-id": "center-04",
                    "enrollment-pattern": "separate",
                    "pipeline-adcid": 4,
                }
            ],
            datatypes=[
                DatatypeConfig(name="clinical", mode="aggregation"),
                DatatypeConfig(name="imaging", mode="aggregation"),
                DatatypeConfig(name="csv", mode="distribution"),
            ],
            study_type="affiliated",
            legacy=True,
        )

        # Verify study was created successfully
        assert study.name == "Mixed Mode Study"
        assert study.study_id == "mixed-study"

        # Verify datatype modes
        assert study.get_datatype_mode("clinical") == "aggregation"
        assert study.get_datatype_mode("imaging") == "aggregation"
        assert study.get_datatype_mode("csv") == "distribution"

        # Verify get_datatypes_by_mode works correctly
        agg_datatypes = study.get_datatypes_by_mode("aggregation")
        dist_datatypes = study.get_datatypes_by_mode("distribution")
        assert set(agg_datatypes) == {"clinical", "imaging"}
        assert set(dist_datatypes) == {"csv"}

        # Create visitor and verify project structure
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Setup mocks
        mock_group = Mock()
        mock_group.id = "center-04"
        mock_group.label = "Center 04"
        mock_flywheel_proxy.find_group.return_value = mock_group

        mock_center = Mock()
        mock_center.id = "center-04"
        mock_center.adcid = 4
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        created_projects = []

        def track_project_creation(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            created_projects.append(label)
            return project

        mock_center.add_project.side_effect = track_project_creation

        with (
            patch(
                "projects.study_mapping.CenterGroup.create_from_group_adaptor",
                return_value=mock_center,
            ),
            patch("projects.study_mapping.StudyGroup.create"),
        ):
            visitor.visit_study(study)

        # Verify aggregation projects for clinical and imaging
        assert "accepted-mixed-study" in created_projects
        assert "ingest-clinical-mixed-study" in created_projects
        assert "sandbox-clinical-mixed-study" in created_projects
        assert "ingest-imaging-mixed-study" in created_projects
        assert "sandbox-imaging-mixed-study" in created_projects

        # Verify distribution project for csv
        assert "distribution-csv-mixed-study" in created_projects

        # Verify no cross-contamination
        assert "distribution-clinical-mixed-study" not in created_projects
        assert "ingest-csv-mixed-study" not in created_projects

    def test_study_with_dashboards_old_format(self, mock_flywheel_proxy):
        """Test study with dashboards in old format.

        This test verifies that old dashboard format (list of strings)
        defaults to center level and creates projects correctly.

        Validates Requirements 7.1, 7.4
        """
        # Create study with old dashboard format
        study = StudyModel(
            name="Dashboard Study",  # pyright: ignore[reportCallIssue]
            study_id="dash-study",
            centers=["center-05"],
            datatypes=["form"],
            mode="aggregation",
            dashboards=["qc-status", "data-entry"],  # Old format
            study_type="primary",
            legacy=False,
        )

        # Verify dashboards were migrated to new format with default level
        dashboard_configs = study.get_dashboard_configs()
        assert len(dashboard_configs) == 2
        assert all(config.level == "center" for config in dashboard_configs)

        # Create visitor and verify project structure
        visitor = StudyMappingVisitor(
            flywheel_proxy=mock_flywheel_proxy, admin_permissions=[]
        )

        # Setup mocks
        mock_group = Mock()
        mock_group.id = "center-05"
        mock_group.label = "Center 05"
        mock_flywheel_proxy.find_group.return_value = mock_group

        mock_center = Mock()
        mock_center.id = "center-05"
        mock_center.adcid = 5
        mock_center.is_active.return_value = True
        mock_center.get_project_info.return_value = Mock()
        mock_center.get_project_info.return_value.get.return_value = None

        created_projects = []

        def track_project_creation(label):
            project = Mock()
            project.id = f"project-{label}"
            project.label = label
            created_projects.append(label)
            return project

        mock_center.add_project.side_effect = track_project_creation

        with patch(
            "projects.study_mapping.CenterGroup.create_from_group_adaptor",
            return_value=mock_center,
        ):
            visitor.visit_study(study)

        # Verify dashboards were created at center level
        assert "dashboard-qc-status" in created_projects
        assert "dashboard-data-entry" in created_projects

        # Verify regular projects were also created
        assert "accepted" in created_projects
        assert "ingest-form" in created_projects
        assert "sandbox-form" in created_projects

    def test_study_with_funding_organization(self):
        """Test study with funding_organization field.

        This test verifies that the new funding_organization field
        is properly stored and retrieved.

        Validates Requirements 7.1
        """
        # Create study with funding_organization
        study = StudyModel(
            name="Funded Study",  # pyright: ignore[reportCallIssue]
            study_id="funded-study",
            centers=["center-06"],
            datatypes=["form"],
            mode="aggregation",
            study_type="primary",
            legacy=False,
            funding_organization="nih-niaaa",
        )

        # Verify funding_organization is stored
        assert study.funding_organization == "nih-niaaa"

        # Verify study is otherwise valid
        assert study.name == "Funded Study"
        assert study.study_id == "funded-study"
        assert study.study_type == "primary"
