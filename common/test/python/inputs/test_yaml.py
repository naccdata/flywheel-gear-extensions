"""Tests for handling of YAML documents."""

from io import StringIO
from typing import Any, List

import pytest
import yaml
from inputs.yaml import load_all_from_stream, load_from_stream


@pytest.fixture
def single_object():
    yield ("---\nk1: v1\nk2: v2\n")


@pytest.fixture
def two_objects():
    yield ("---\nk1: v1\nk2: v2\n---\nk1: v1\nk2: v2\n")


@pytest.fixture
def mock_file_open(mocker, two_objects):
    """Mock file open."""
    mocked_data = mocker.mock_open(read_data=two_objects)
    mocker.patch("builtins.open", mocked_data)


# pylint: disable=(too-few-public-methods)
class TestYAML:
    """Test for handling of YAML documents."""

    # pylint: disable=(no-self-use)
    def test_empty(self):
        """Test for empty list.

        Function called returns list of lists.
        """
        empty_list: List[Any] = []
        yaml_object = yaml.safe_dump(
            empty_list, allow_unicode=True, default_flow_style=False
        )
        yaml_stream = StringIO()
        yaml_stream.write(yaml_object)
        object_list = load_all_from_stream(yaml_stream)
        assert object_list is not None
        assert [doc for doc in object_list] == []

        yaml_stream.seek(0)
        yaml_object = load_from_stream(yaml_stream)
        assert yaml_object == []

    def test_load_all(self, two_objects):
        yaml_stream = StringIO()
        yaml_stream.write(two_objects)
        yaml_stream.seek(0)
        yaml_iterator = load_all_from_stream(yaml_stream)
        object_list = [doc for doc in yaml_iterator]
        assert object_list == [{"k1": "v1", "k2": "v2"}, {"k1": "v1", "k2": "v2"}]
