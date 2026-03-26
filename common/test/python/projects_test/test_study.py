"""Tests for projects.*"""

from typing import Optional

import pytest
from projects.study import StudyCenterModel, StudyError, StudyModel, StudyVisitor


class DummyVisitor(StudyVisitor):
    """Visitor for testing apply methods."""

    def __init__(self) -> None:
        self.center_id: Optional[str] = None
        self.project_name: Optional[str] = None
        self.datatype_name: Optional[str] = None

    def visit_center(self, center: StudyCenterModel) -> None:
        self.center_id = center.center_id

    def visit_datatype(self, datatype: str):
        self.datatype_name = datatype

    def visit_study(self, study: StudyModel) -> None:
        self.project_name = study.name


class TestStudy:
    """Tests for Project class."""

    def test_object(self):
        """Tests for object creation."""
        project = StudyModel(
            name="Project Alpha",  # pyright: ignore[reportCallIssue]
            study_id="project-alpha",
            centers=[
                StudyCenterModel(center_id="ac"),
                StudyCenterModel(center_id="bc"),
            ],
            datatypes=["dicom"],
            mode="aggregation",
            published=True,
            study_type="primary",
            legacy=True,
        )
        assert project.study_id == "project-alpha"
        assert project.centers == [
            StudyCenterModel(center_id="ac"),
            StudyCenterModel(center_id="bc"),
        ]
        # After migration, datatypes are DatatypeConfig objects
        from projects.study import DatatypeConfig

        assert isinstance(project.datatypes, list)
        assert len(project.datatypes) == 1
        assert isinstance(project.datatypes[0], DatatypeConfig)
        assert project.datatypes[0].name == "dicom"
        assert project.datatypes[0].mode == "aggregation"
        assert project.mode == "aggregation"
        assert project.is_published()
        assert project.is_primary()

        project2 = StudyModel.create(
            {
                "study": "Project Alpha",
                "study-id": "project-alpha",
                "centers": [
                    "ac",
                    {"center-id": "bc", "enrollment-pattern": "co-enrollment"},
                ],
                "datatypes": ["dicom"],
                "mode": "aggregation",
                "published": True,
                "study-type": "primary",
            }
        )
        assert project == project2

        with pytest.raises(StudyError):
            StudyModel.create({})

    def test_apply(self):
        """Test project apply method."""
        visitor = DummyVisitor()
        project = StudyModel(
            name="Project Beta",  # pyright: ignore[reportCallIssue]
            study_id="beta",
            centers=[],
            datatypes=[],
            mode="aggregation",
            published=True,
            study_type="affiliated",
            legacy=True,
        )
        project.apply(visitor)
        assert visitor.project_name == "Project Beta"

    def test_study_with_dashboards(self):
        """Test study creation with dashboards field."""
        study = StudyModel(
            name="Project with Dashboards",  # pyright: ignore[reportCallIssue]
            study_id="project-dash",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=["form"],
            dashboards=["enrollment", "qc-status"],
            mode="aggregation",
            published=False,
            study_type="primary",
            legacy=True,
        )
        # After migration, dashboards are DashboardConfig objects
        from projects.study import DashboardConfig

        assert study.dashboards is not None
        assert isinstance(study.dashboards, list)
        assert len(study.dashboards) == 2
        assert isinstance(study.dashboards[0], DashboardConfig)
        assert study.dashboards[0].name == "enrollment"
        assert study.dashboards[0].level == "center"
        assert isinstance(study.dashboards[1], DashboardConfig)
        assert study.dashboards[1].name == "qc-status"
        assert study.dashboards[1].level == "center"

    def test_study_without_dashboards(self):
        """Test study creation without dashboards field (should default to
        None)."""
        study = StudyModel(
            name="Project without Dashboards",  # pyright: ignore[reportCallIssue]
            study_id="project-no-dash",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=["form"],
            mode="aggregation",
            published=False,
            study_type="primary",
            legacy=True,
        )
        assert study.dashboards is None

    def test_study_with_empty_dashboards(self):
        """Test study creation with empty dashboards list."""
        study = StudyModel(
            name="Project with Empty Dashboards",  # pyright: ignore[reportCallIssue]
            study_id="project-empty-dash",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=["form"],
            dashboards=[],
            mode="aggregation",
            published=False,
            study_type="primary",
            legacy=True,
        )
        assert study.dashboards == []

    def test_study_dashboards_from_dict(self):
        """Test study creation from dict with dashboards."""
        study = StudyModel.create(
            {
                "study": "Project Alpha",
                "study-id": "project-alpha",
                "centers": ["ac"],
                "datatypes": ["form"],
                "dashboards": ["enrollment", "qc-status"],
                "mode": "aggregation",
                "published": False,
                "study-type": "primary",
            }
        )
        # After migration, dashboards are DashboardConfig objects
        from projects.study import DashboardConfig

        assert study.dashboards is not None
        assert isinstance(study.dashboards, list)
        assert len(study.dashboards) == 2
        assert isinstance(study.dashboards[0], DashboardConfig)
        assert study.dashboards[0].name == "enrollment"
        assert study.dashboards[0].level == "center"
        assert isinstance(study.dashboards[1], DashboardConfig)
        assert study.dashboards[1].name == "qc-status"
        assert study.dashboards[1].level == "center"

    def test_study_with_pages(self):
        """Test study creation with pages field."""
        study = StudyModel(
            name="Project with Pages",  # pyright: ignore[reportCallIssue]
            study_id="project-pages",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=["form"],
            pages=["overview", "data-entry", "reports"],
            mode="aggregation",
            published=False,
            study_type="primary",
            legacy=True,
        )
        assert study.pages == ["overview", "data-entry", "reports"]

    def test_study_without_pages(self):
        """Test study creation without pages field (should default to None)."""
        study = StudyModel(
            name="Project without Pages",  # pyright: ignore[reportCallIssue]
            study_id="project-no-pages",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=["form"],
            mode="aggregation",
            published=False,
            study_type="primary",
            legacy=True,
        )
        assert study.pages is None

    def test_study_with_empty_pages(self):
        """Test study creation with empty pages list."""
        study = StudyModel(
            name="Project with Empty Pages",  # pyright: ignore[reportCallIssue]
            study_id="project-empty-pages",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=["form"],
            pages=[],
            mode="aggregation",
            published=False,
            study_type="primary",
            legacy=True,
        )
        assert study.pages == []

    def test_study_pages_from_dict(self):
        """Test study creation from dict with pages."""
        study = StudyModel.create(
            {
                "study": "Project Alpha",
                "study-id": "project-alpha",
                "centers": ["ac"],
                "datatypes": ["form"],
                "pages": ["overview", "data-entry", "reports"],
                "mode": "aggregation",
                "published": False,
                "study-type": "primary",
            }
        )
        assert study.pages == ["overview", "data-entry", "reports"]

    def test_study_pages_validation_rejects_invalid_types(self):
        """Test that validation rejects invalid page types."""
        # Test with non-string items in list
        with pytest.raises(StudyError):
            StudyModel.create(
                {
                    "study": "Project Invalid Pages",
                    "study-id": "project-invalid",
                    "centers": ["ac"],
                    "datatypes": ["form"],
                    "pages": ["valid-page", 123, "another-page"],
                    "mode": "aggregation",
                    "published": False,
                    "study-type": "primary",
                }
            )

    def test_study_pages_validation_rejects_non_list(self):
        """Test that validation rejects non-list pages value."""
        with pytest.raises(StudyError):
            StudyModel.create(
                {
                    "study": "Project Invalid Pages Type",
                    "study-id": "project-invalid-type",
                    "centers": ["ac"],
                    "datatypes": ["form"],
                    "pages": "not-a-list",
                    "mode": "aggregation",
                    "published": False,
                    "study-type": "primary",
                }
            )


class TestStudyModelValidation:
    """Tests for StudyModel validation logic (Task 3.4)."""

    def test_migration_from_old_format_to_new_format(self):
        """Test migration from study-level mode to datatype-level modes."""
        # Old format: study-level mode with list of datatype strings
        study = StudyModel.create(
            {
                "study": "Test Study",
                "study-id": "test",
                "centers": ["ac"],
                "mode": "aggregation",
                "datatypes": ["form", "dicom", "csv"],
                "study-type": "primary",
            }
        )

        from projects.study import DatatypeConfig

        # Verify migration happened
        assert isinstance(study.datatypes, list)
        assert len(study.datatypes) == 3
        assert all(isinstance(dt, DatatypeConfig) for dt in study.datatypes)
        assert study.datatypes[0].name == "form"  # type: ignore[union-attr]
        assert study.datatypes[0].mode == "aggregation"  # type: ignore[union-attr]
        assert study.datatypes[1].name == "dicom"  # type: ignore[union-attr]
        assert study.datatypes[1].mode == "aggregation"  # type: ignore[union-attr]
        assert study.datatypes[2].name == "csv"  # type: ignore[union-attr]
        assert study.datatypes[2].mode == "aggregation"  # type: ignore[union-attr]

    def test_primary_study_validation_aggregation_only(self):
        """Test that primary studies must have aggregation-only datatypes."""
        # Valid: primary study with all aggregation datatypes
        study = StudyModel.create(
            {
                "study": "Primary Study",
                "study-id": "primary",
                "centers": ["ac"],
                "datatypes": [
                    {"name": "form", "mode": "aggregation"},
                    {"name": "dicom", "mode": "aggregation"},
                ],
                "study-type": "primary",
            }
        )
        assert study.study_type == "primary"

        # Invalid: primary study with distribution datatype
        with pytest.raises(StudyError) as exc_info:
            StudyModel.create(
                {
                    "study": "Invalid Primary",
                    "study-id": "invalid",
                    "centers": ["ac"],
                    "datatypes": [
                        {"name": "form", "mode": "aggregation"},
                        {"name": "csv", "mode": "distribution"},
                    ],
                    "study-type": "primary",
                }
            )
        assert (
            "Primary study cannot have datatype 'csv' with mode 'distribution'"
            in str(exc_info.value)
        )

    def test_affiliated_study_with_mixed_modes(self):
        """Test that affiliated studies can have mixed modes."""
        study = StudyModel.create(
            {
                "study": "Affiliated Study",
                "study-id": "affiliated",
                "centers": ["ac"],
                "datatypes": [
                    {"name": "form", "mode": "aggregation"},
                    {"name": "dicom", "mode": "aggregation"},
                    {"name": "csv", "mode": "distribution"},
                ],
                "study-type": "affiliated",
            }
        )
        assert study.study_type == "affiliated"
        assert len(study.datatypes) == 3
        assert study.get_datatypes_by_mode("aggregation") == ["form", "dicom"]
        assert study.get_datatypes_by_mode("distribution") == ["csv"]

    def test_validation_error_messages_invalid_mode(self):
        """Test that validation error messages are clear for invalid modes."""
        with pytest.raises(StudyError) as exc_info:
            StudyModel.create(
                {
                    "study": "Invalid Mode",
                    "study-id": "invalid",
                    "centers": ["ac"],
                    "datatypes": [{"name": "form", "mode": "invalid-mode"}],
                    "study-type": "primary",
                }
            )
        assert "Invalid mode 'invalid-mode'" in str(exc_info.value)
        assert "Mode must be 'aggregation' or 'distribution'" in str(exc_info.value)

    def test_validation_error_messages_missing_mode(self):
        """Test error message when mode is missing in datatype config."""
        with pytest.raises(StudyError) as exc_info:
            StudyModel.create(
                {
                    "study": "Missing Mode",
                    "study-id": "missing",
                    "centers": ["ac"],
                    "datatypes": [{"name": "form"}],
                    "study-type": "primary",
                }
            )
        assert "missing 'mode' field" in str(exc_info.value)

    def test_validation_error_messages_missing_study_mode(self):
        """Test error when using old format without study-level mode."""
        with pytest.raises(StudyError) as exc_info:
            StudyModel.create(
                {
                    "study": "No Mode",
                    "study-id": "no-mode",
                    "centers": ["ac"],
                    "datatypes": ["form", "dicom"],
                    "study-type": "primary",
                }
            )
        assert "requires study-level 'mode' field" in str(exc_info.value)

    def test_edge_case_single_datatype(self):
        """Test with single datatype."""
        study = StudyModel.create(
            {
                "study": "Single Datatype",
                "study-id": "single",
                "centers": ["ac"],
                "mode": "aggregation",
                "datatypes": ["form"],
                "study-type": "primary",
            }
        )
        assert len(study.datatypes) == 1
        assert study.datatypes[0].name == "form"  # type: ignore[union-attr]
        assert study.datatypes[0].mode == "aggregation"  # type: ignore[union-attr]

    def test_edge_case_all_same_mode(self):
        """Test with all datatypes having the same mode."""
        study = StudyModel.create(
            {
                "study": "All Aggregation",
                "study-id": "all-agg",
                "centers": ["ac"],
                "datatypes": [
                    {"name": "form", "mode": "aggregation"},
                    {"name": "dicom", "mode": "aggregation"},
                    {"name": "csv", "mode": "aggregation"},
                ],
                "study-type": "affiliated",
            }
        )
        assert len(study.datatypes) == 3
        assert study.get_datatypes_by_mode("aggregation") == ["form", "dicom", "csv"]
        assert study.get_datatypes_by_mode("distribution") == []

    def test_dashboard_migration_from_old_format(self):
        """Test dashboard migration from list of strings to DashboardConfig."""
        study = StudyModel.create(
            {
                "study": "Dashboard Migration",
                "study-id": "dash-migrate",
                "centers": ["ac"],
                "mode": "aggregation",
                "datatypes": ["form"],
                "dashboards": ["enrollment", "qc-status"],
                "study-type": "primary",
            }
        )

        from projects.study import DashboardConfig

        assert study.dashboards is not None
        assert len(study.dashboards) == 2
        assert all(isinstance(db, DashboardConfig) for db in study.dashboards)
        assert study.dashboards[0].name == "enrollment"  # type: ignore[union-attr]
        assert study.dashboards[0].level == "center"  # type: ignore[union-attr]
        assert study.dashboards[1].name == "qc-status"  # type: ignore[union-attr]
        assert study.dashboards[1].level == "center"  # type: ignore[union-attr]

    def test_dashboard_new_format_with_levels(self):
        """Test dashboard configuration with explicit levels."""
        from projects.study import DashboardConfig

        study = StudyModel.create(
            {
                "study": "Dashboard Levels",
                "study-id": "dash-levels",
                "centers": ["ac"],
                "mode": "aggregation",
                "datatypes": ["form"],
                "dashboards": [
                    {"name": "enrollment", "level": "center"},
                    {"name": "study-overview", "level": "study"},
                ],
                "study-type": "primary",
            }
        )

        assert study.dashboards is not None
        assert len(study.dashboards) == 2
        assert isinstance(study.dashboards[0], DashboardConfig)
        assert study.dashboards[0].name == "enrollment"  # type: ignore[union-attr]
        assert study.dashboards[0].level == "center"  # type: ignore[union-attr]
        assert isinstance(study.dashboards[1], DashboardConfig)
        assert study.dashboards[1].name == "study-overview"  # type: ignore[union-attr]
        assert study.dashboards[1].level == "study"  # type: ignore[union-attr]

    def test_dashboard_invalid_level(self):
        """Test that invalid dashboard levels are rejected."""
        with pytest.raises(StudyError) as exc_info:
            StudyModel.create(
                {
                    "study": "Invalid Dashboard Level",
                    "study-id": "invalid-dash",
                    "centers": ["ac"],
                    "mode": "aggregation",
                    "datatypes": ["form"],
                    "dashboards": [{"name": "test", "level": "invalid"}],
                    "study-type": "primary",
                }
            )
        assert "Invalid level 'invalid'" in str(exc_info.value)
        assert "Level must be 'center' or 'study'" in str(exc_info.value)


class TestStudyModelSerialization:
    """Tests for StudyModel serialization and deserialization (Task 4)."""

    def test_datatype_config_serialization_to_dict(self):
        """Test DatatypeConfig serialization to dict format."""
        from projects.study import DatatypeConfig

        config = DatatypeConfig(name="form", mode="aggregation")
        serialized = config.model_dump()

        assert serialized["name"] == "form"
        assert serialized["mode"] == "aggregation"

    def test_datatype_config_serialization_with_kebab_case(self):
        """Test DatatypeConfig serialization with kebab-case aliases."""
        from projects.study import DatatypeConfig

        config = DatatypeConfig(name="form", mode="aggregation")
        serialized = config.model_dump(by_alias=True)

        # Verify kebab-case aliases are used
        assert serialized["name"] == "form"
        assert serialized["mode"] == "aggregation"

    def test_datatype_config_deserialization_from_dict(self):
        """Test DatatypeConfig deserialization from dict format."""
        from projects.study import DatatypeConfig

        data = {"name": "dicom", "mode": "distribution"}
        config = DatatypeConfig.model_validate(data)

        assert config.name == "dicom"
        assert config.mode == "distribution"

    def test_datatype_config_deserialization_with_kebab_case(self):
        """Test DatatypeConfig deserialization with kebab-case field names."""
        from projects.study import DatatypeConfig

        # Using kebab-case field names (though these fields don't have hyphens)
        data = {"name": "csv", "mode": "aggregation"}
        config = DatatypeConfig.model_validate(data)

        assert config.name == "csv"
        assert config.mode == "aggregation"

    def test_dashboard_config_serialization_to_dict(self):
        """Test DashboardConfig serialization to dict format."""
        from projects.study import DashboardConfig

        config = DashboardConfig(name="enrollment", level="center")
        serialized = config.model_dump()

        assert serialized["name"] == "enrollment"
        assert serialized["level"] == "center"

    def test_dashboard_config_serialization_with_default_level(self):
        """Test DashboardConfig serialization with default level."""
        from projects.study import DashboardConfig

        config = DashboardConfig(name="qc-status")
        serialized = config.model_dump()

        assert serialized["name"] == "qc-status"
        assert serialized["level"] == "center"  # Default value

    def test_dashboard_config_serialization_with_kebab_case(self):
        """Test DashboardConfig serialization with kebab-case aliases."""
        from projects.study import DashboardConfig

        config = DashboardConfig(name="study-overview", level="study")
        serialized = config.model_dump(by_alias=True)

        # Verify kebab-case aliases are used
        assert serialized["name"] == "study-overview"
        assert serialized["level"] == "study"

    def test_dashboard_config_deserialization_from_dict(self):
        """Test DashboardConfig deserialization from dict format."""
        from projects.study import DashboardConfig

        data = {"name": "enrollment", "level": "center"}
        config = DashboardConfig.model_validate(data)

        assert config.name == "enrollment"
        assert config.level == "center"

    def test_dashboard_config_deserialization_with_default_level(self):
        """Test DashboardConfig deserialization applies default level."""
        from projects.study import DashboardConfig

        data = {"name": "qc-status"}
        config = DashboardConfig.model_validate(data)

        assert config.name == "qc-status"
        assert config.level == "center"  # Default value applied

    def test_funding_organization_serialization_when_present(self):
        """Test funding_organization field serialization when present."""
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=[{"name": "form", "mode": "aggregation"}],
            study_type="primary",
            funding_organization="nih-niaaa",
        )

        serialized = study.model_dump()
        assert serialized["funding_organization"] == "nih-niaaa"

    def test_funding_organization_serialization_when_absent(self):
        """Test funding_organization field serialization when absent."""
        study = StudyModel(
            name="Test Study",  # pyright: ignore[reportCallIssue]
            study_id="test",
            centers=[StudyCenterModel(center_id="ac")],
            datatypes=[{"name": "form", "mode": "aggregation"}],
            study_type="primary",
        )

        serialized = study.model_dump()
        assert serialized["funding_organization"] is None

    def test_funding_organization_deserialization_when_present(self):
        """Test funding_organization field deserialization when present."""
        study = StudyModel.create(
            {
                "study": "Test Study",
                "study-id": "test",
                "centers": ["ac"],
                "datatypes": [{"name": "form", "mode": "aggregation"}],
                "study-type": "primary",
                "funding-organization": "nih-ninds",
            }
        )

        assert study.funding_organization == "nih-ninds"

    def test_funding_organization_deserialization_when_absent(self):
        """Test funding_organization field deserialization when absent."""
        study = StudyModel.create(
            {
                "study": "Test Study",
                "study-id": "test",
                "centers": ["ac"],
                "datatypes": [{"name": "form", "mode": "aggregation"}],
                "study-type": "primary",
            }
        )

        assert study.funding_organization is None

    def test_funding_organization_deserialization_when_none(self):
        """Test funding_organization field deserialization when explicitly
        None."""
        study = StudyModel.create(
            {
                "study": "Test Study",
                "study-id": "test",
                "centers": ["ac"],
                "datatypes": [{"name": "form", "mode": "aggregation"}],
                "study-type": "primary",
                "funding-organization": None,
            }
        )

        assert study.funding_organization is None


class TestStudyCenterModel:
    def test_validation(self):
        # valid
        StudyCenterModel(
            center_id="one", pipeline_adcid=0, enrollment_pattern="separate"
        )

        # valid
        StudyCenterModel(
            center_id="two", pipeline_adcid=None, enrollment_pattern="co-enrollment"
        )

        # invalid
        with pytest.raises(ValueError):
            StudyCenterModel(
                center_id="three", pipeline_adcid=None, enrollment_pattern="separate"
            )
