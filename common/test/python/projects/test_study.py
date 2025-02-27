"""Tests for projects.*"""
from typing import Optional

import pytest
from projects.study import Study, StudyVisitor


class DummyVisitor(StudyVisitor):
    """Visitor for testing apply methods."""

    def __init__(self) -> None:
        self.center_id: Optional[str] = None
        self.project_name: Optional[str] = None
        self.datatype_name: Optional[str] = None

    def visit_center(self, center_id: str) -> None:
        self.center_id = center_id

    def visit_datatype(self, datatype: str):
        self.datatype_name = datatype

    def visit_study(self, study: Study) -> None:
        self.project_name = study.name


class TestStudy:
    """Tests for Project class."""

    def test_object(self):
        """Tests for object creation."""
        project = Study(name="Project Alpha",
                        study_id='project-alpha',
                        centers=['ac'],
                        datatypes=['dicom'],
                        mode='aggregation',
                        published=True,
                        primary=True)
        assert project.study_id == "project-alpha"
        assert project.centers == ['ac']
        assert project.datatypes == ['dicom']
        assert project.mode == 'aggregation'
        assert project.is_published()
        assert project.is_primary()

        project2 = Study.create({
            'study': 'Project Alpha',
            'study-id': 'project-alpha',
            'centers': ['ac'],
            'datatypes': ['dicom'],
            'mode': 'aggregation',
            'published': True,
            'primary': True
        })
        assert project == project2

        with pytest.raises(KeyError):
            Study.create({})

    def test_apply(self):
        """Test project apply method."""
        visitor = DummyVisitor()
        project = Study(name='Project Beta',
                        study_id='beta',
                        centers=[],
                        datatypes=[],
                        mode='aggregation',
                        published=True)
        project.apply(visitor)
        assert visitor.project_name == 'Project Beta'
