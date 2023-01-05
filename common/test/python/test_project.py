"""Tests for projects.*"""
from typing import Optional

import pytest
from projects.project import Center, Project, ProjectVisitor


class DummyVisitor(ProjectVisitor):
    """Visitor for testing apply methods."""

    def __init__(self) -> None:
        self.center_name: Optional[str] = None
        self.project_name: Optional[str] = None
        self.datatype_name: Optional[str] = None

    def visit_center(self, center: Center) -> None:
        self.center_name = center.name

    def visit_datatype(self, datatype: str):
        self.datatype_name = datatype

    def visit_project(self, project: Project) -> None:
        self.project_name = project.name


# pylint: disable=(no-self-use)
class TestCenter:
    """Tests for projects.Center."""

    def test_object(self):
        """Sanity check on object creation and properties."""
        center = Center(adcid=7, name="Alpha ADRC", center_id='alpha-adrc')
        assert center.adcid == 7
        assert center.name == "Alpha ADRC"
        assert center.is_active()
        assert center.center_id == 'alpha-adrc'

    def test_create(self):
        """Check that create method creates object correctly."""
        center = Center.create({
            'adc-id': 7,
            'name': 'Alpha ADRC',
            'center-id': 'alpha-adrc',
            'is-active': True
        })
        center2 = Center(adcid=7, name="Alpha ADRC", center_id='alpha-adrc')
        assert center == center2

        with pytest.raises(KeyError):
            Center.create({})

    def test_apply(self):
        """Test that visitor applied."""
        visitor = DummyVisitor()
        center = Center(adcid=1, name="Dummy Center", center_id="dummy")
        center.apply(visitor)
        assert visitor.center_name == "Dummy Center"


class TestProject:
    """Tests for Project class."""

    def test_object(self):
        """Tests for object creation."""
        project = Project(name="Project Alpha",
                          project_id='project-alpha',
                          centers=[
                              Center(adcid=1,
                                     name='A Center',
                                     center_id='ac',
                                     active=True)
                          ],
                          datatypes=['dicom'],
                          published=True,
                          primary=True)
        assert project.project_id == "project-alpha"
        assert project.centers == [
            Center(adcid=1, name='A Center', center_id='ac', active=True)
        ]
        assert project.datatypes == ['dicom']
        assert project.is_published()
        assert project.is_primary()

        project2 = Project.create({
            'project':
            'Project Alpha',
            'project-id':
            'project-alpha',
            'centers': [{
                'adc-id': 1,
                'name': 'A Center',
                'center-id': 'ac',
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
            Project.create({})

    def test_apply(self):
        """Test project apply method."""
        visitor = DummyVisitor()
        project = Project(name='Project Beta',
                          project_id='beta',
                          centers=[],
                          datatypes=[],
                          published=True)
        project.apply(visitor)
        assert visitor.project_name == 'Project Beta'
