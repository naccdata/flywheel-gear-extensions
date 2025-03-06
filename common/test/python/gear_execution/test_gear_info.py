"""Tests the GearInfo and GearConfigs pydantic classes."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from gear_execution.gear_trigger import GearConfigs, GearInfo

TEST_FILES_DIR = Path(__file__).parent.resolve() / 'data'


class DummyGearConfigs(GearConfigs):

    test_str: str
    test_int: int
    test_list: List[Any]
    test_optional: Optional[str] = 'optional'


class TestGearInfo:
    """Tests the GearInfo and GearConfigs pydantic classes."""

    def test_basic_create(self):
        """Test a basic create with default GearConfigs class."""

        # assert that when empty fails/returns None
        assert GearInfo.load_from_file(str(TEST_FILES_DIR /
                                           'empty-file.json')) is None
        """
        CH - removed this test
        made apikey_path_prefix optional to support non-gearbot gears

        # assert without apikey_path_prefix fails/returns None
        assert GearInfo.load_from_file(str(TEST_FILES_DIR /
                                           'no-configs.json')) is None
        assert GearInfo.load_from_file(
            str(TEST_FILES_DIR / 'empty-configs.json')) is None """

        # now assert that it matches
        result = GearInfo.load_from_file(
            str(TEST_FILES_DIR / 'basic-configs.json'))

        assert result is not None
        assert result.model_dump() == {
            "gear_name": "basic-configs",
            "configs": {
                "apikey_path_prefix": "/test/dummy/gearbot"
            }
        }

    def test_custom_create(self):
        """Test a create with custom GearConfigs class."""
        # assert that without apikey_path_prefix this fails/returns None
        assert GearInfo.load_from_file(
            str(TEST_FILES_DIR / 'custom-configs-invalid.json'),
            DummyGearConfigs) is None

        # assert that without test_int this still fails/returns None
        assert GearInfo.load_from_file(
            str(TEST_FILES_DIR / 'custom-configs-invalid-2.json'),
            DummyGearConfigs) is None

        # now make sure that this passes
        result = GearInfo.load_from_file(
            str(TEST_FILES_DIR / 'custom-configs.json'), DummyGearConfigs)
        assert result is not None

        # however output will not be exactly the same, since test_optional
        # was not explicitly passed; test the behavior is as expected
        configs: Dict[str, Any] = {
            "gear_name": "custom-configs",
            "configs": {
                "test_str": "hello",
                "test_int": 1,
                "test_list": [{
                    "key": "value"
                }, 2, "world"],
                "apikey_path_prefix": "/test/dummy/gearbot"
            }
        }

        assert result.configs.test_optional == 'optional'
        assert result.model_dump() != configs
        configs['configs']['test_optional'] = 'optional'
        assert result.model_dump() == configs
