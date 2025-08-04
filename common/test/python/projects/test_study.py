"""Tests for projects.*"""

from typing import Optional

import pytest
from projects.study import CenterStudyModel, StudyError, StudyModel, StudyVisitor


class DummyVisitor(StudyVisitor):
    """Visitor for testing apply methods."""

    def __init__(self) -> None:
        self.center_id: Optional[str] = None
        self.project_name: Optional[str] = None
        self.datatype_name: Optional[str] = None

    def visit_center(self, center: CenterStudyModel) -> None:
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
            study="Project Alpha",
            study_id="project-alpha",
            centers=[
                CenterStudyModel(center_id="ac"),
                CenterStudyModel(center_id="bc"),
            ],
            datatypes=["dicom"],
            mode="aggregation",
            published=True,
            study_type="primary",
            legacy=True,
        )
        assert project.study_id == "project-alpha"
        assert project.centers == [
            CenterStudyModel(center_id="ac"),
            CenterStudyModel(center_id="bc"),
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
            study="Project Beta",
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
