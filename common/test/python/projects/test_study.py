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
        assert project.datatypes == ["dicom"]
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
        assert study.dashboards == ["enrollment", "qc-status"]

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
        assert study.dashboards == ["enrollment", "qc-status"]

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
