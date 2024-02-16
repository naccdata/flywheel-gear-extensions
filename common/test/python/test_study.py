"""Tests for projects.*"""
from typing import Optional

import pytest
from projects.study import Center, Study, StudyVisitor


class DummyVisitor(StudyVisitor):
    """Visitor for testing apply methods."""

    def __init__(self) -> None:
        self.center_name: Optional[str] = None
        self.project_name: Optional[str] = None
        self.datatype_name: Optional[str] = None

    def visit_center(self, center: Center) -> None:
        self.center_name = center.name

    def visit_datatype(self, datatype: str):
        self.datatype_name = datatype

    def visit_study(self, study: Study) -> None:
        self.project_name = study.name


# pylint: disable=(no-self-use)
class TestCenter:
    """Tests for projects.Center."""

    def test_object(self):
        """Sanity check on object creation and properties."""
        center = Center(tags=['adcid-7'],
                        name="Alpha ADRC",
                        center_id='alpha-adrc',
                        adcid=7)
        assert 'adcid-7' in center.tags
        assert center.name == "Alpha ADRC"
        assert center.is_active()
        assert center.center_id == 'alpha-adrc'

    def test_create(self):
        """Check that create method creates object correctly."""
        center = Center.create({
            'tags': ['adcid-7'],
            'name': 'Alpha ADRC',
            'center-id': 'alpha-adrc',
            'adcid': 7,
            'is-active': True
        })
        center2 = Center(tags=['adcid-7'],
                         name="Alpha ADRC",
                         center_id='alpha-adrc',
                         adcid=7)
        assert center == center2

        with pytest.raises(KeyError):
            Center.create({})

    def test_apply(self):
        """Test that visitor applied."""
        visitor = DummyVisitor()
        center = Center(tags=['adcid-1'],
                        name="Dummy Center",
                        center_id="dummy",
                        adcid=1)
        center.apply(visitor)
        assert visitor.center_name == "Dummy Center"


class TestProject:
    """Tests for Project class."""

    def test_object(self):
        """Tests for object creation."""
        project = Study(name="Project Alpha",
                        study_label='project-alpha',
                        centers=[
                            Center(tags=['adcid-1'],
                                   name='A Center',
                                   center_id='ac',
                                   adcid=1,
                                   active=True)
                        ],
                        datatypes=['dicom'],
                        published=True,
                        primary=True)
        assert project.study_label == "project-alpha"
        assert project.centers == [
            Center(tags=['adcid-1'],
                   name='A Center',
                   center_id='ac',
                   adcid=1,
                   active=True)
        ]
        assert project.datatypes == ['dicom']
        assert project.is_published()
        assert project.is_primary()

        project2 = Study.create({
            'project':
            'Project Alpha',
            'project-label':
            'project-alpha',
            'centers': [{
                'tags': ['adcid-1'],
                'name': 'A Center',
                'center-id': 'ac',
                'adcid': 1,
                'is-active': True
            }],
            'datatypes': ['dicom'],
            'published':
            True,
            'primary':
            True
        })
        assert project == project2

        with pytest.raises(KeyError):
            Study.create({})

    def test_apply(self):
        """Test project apply method."""
        visitor = DummyVisitor()
        project = Study(name='Project Beta',
                        study_label='beta',
                        centers=[],
                        datatypes=[],
                        published=True)
        project.apply(visitor)
        assert visitor.project_name == 'Project Beta'
