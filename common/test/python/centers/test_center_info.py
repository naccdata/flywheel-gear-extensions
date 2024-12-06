"""Tests for centers.center_info."""
from typing import Optional

import pytest
import yaml
from centers.center_info import CenterInfo, CenterMapInfo
from projects.study import Study, StudyVisitor
from pydantic import ValidationError


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


@pytest.fixture(scope='module')
def dummy_center():
    """Generate dummy CenterInfo for general testing."""
    return CenterInfo(tags=['adcid-7'],
                      name="Alpha ADRC",
                      group='alpha-adrc',
                      adcid=7)


@pytest.fixture(scope='function')
def dummy_center_map(dummy_center):
    """Generate dummy CenterMapInfo for general testing."""
    return CenterMapInfo(centers={7: dummy_center})


# pylint: disable=(no-self-use)
class TestCenterInfo:
    """Tests for centers.center_info.CenterInfo."""

    def test_object(self, dummy_center):
        """Sanity check on object creation and properties."""
        assert 'adcid-7' in dummy_center.tags
        assert dummy_center.name == "Alpha ADRC"
        assert dummy_center.active
        assert dummy_center.group == 'alpha-adrc'

    def test_create(self, dummy_center):
        """Check that model is created correctly from dict, and the equality
        matches."""
        center = CenterInfo(
            **{
                'tags': ['adcid-7'],
                'name': 'Alpha ADRC',
                'center-id': 'alpha-adrc',
                'adcid': 7,
                'is-active': True
            })
        assert center == dummy_center

    def test_invalid_creation(self):
        """Test invalid creation."""
        with pytest.raises(ValidationError):
            CenterInfo()

        with pytest.raises(ValidationError):
            CenterInfo(tags=['adcid-7'], name="Alpha ADRC", adcid=7)

    def test_apply(self, dummy_center):
        """Test that visitor applied."""
        visitor = DummyVisitor()
        dummy_center.apply(visitor)
        assert visitor.center_id == "alpha-adrc"

    def test_create_from_yaml(self, dummy_center):
        """Test creation from yaml."""
        center_yaml = ("adcid: 7\n"
                       "name: Alpha ADRC\n"
                       "center-id: alpha-adrc\n"
                       "is-active: True")
        center_gen = yaml.safe_load_all(center_yaml)
        center = CenterInfo(**next(iter(center_gen)))
        assert center == dummy_center

    def test_repr(self, dummy_center):
        """Test representation."""
        assert repr(dummy_center) == ("Center(group=alpha-adrc, "
                                      "name=Alpha ADRC, "
                                      "adcid=7, "
                                      "active=True, "
                                      "tags=('adcid-7',)")


# pylint: disable=(no-self-use)
class TestCenterMapInfo:
    """Tests for centers.center_info.CenterMapInfo."""

    def test_creation(self, dummy_center, dummy_center_map):
        """Test creation."""
        assert dummy_center_map.centers == {7: dummy_center}

        assert CenterMapInfo(centers={}).centers == {}

    def test_add(self, dummy_center, dummy_center_map):
        """Test adding."""
        dummy_center_map.add(8, dummy_center)
        assert dummy_center_map.centers == {7: dummy_center, 8: dummy_center}

    def test_get(self, dummy_center, dummy_center_map):
        """Test getting."""
        assert dummy_center_map.get(7) == dummy_center
        assert not dummy_center_map.get(1)
