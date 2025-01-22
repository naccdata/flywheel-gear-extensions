"""Tests the GearInfo and GearConfigs pydantic classes."""
import copy
from typing import Any, Dict, List, Optional

from gear_execution.gear_trigger import GearConfigs, GearInfo


class DummyGearConfigs(GearConfigs):

    test_str: str
    test_int: int
    test_list: List[Any]
    test_optional: Optional[str] = 'optional'


class TestGearInfo:
    """Tests the GearInfo and GearConfigs pydantic classes."""

    def test_basic_create(self):
        """Test a basic create with default GearConfigs class."""
        configs: Dict[str, Any] = {'gear_name': 'dummy-gear'}

        # assert that when empty/without apikey_path_prefix this
        # fails/returns None
        assert GearInfo.load_from_file({}) is None
        assert GearInfo.load_from_file(configs) is None
        configs['configs'] = {}
        assert GearInfo.load_from_file(configs) is None

        # now assert that it matches
        configs['configs']['apikey_path_prefix'] = '/test/dummy/gearbot'
        result = GearInfo.load_from_file(copy.deepcopy(configs))

        assert result is not None
        assert result.model_dump() == configs

    def test_custom_create(self):
        """Test a create with custom GearConfigs class."""
        configs: Dict[str, Any] = {
            'gear_name': 'dummy-gear-2',
            'configs': {
                'test_str': 'hello',
                'test_list': [{
                    'key': 'value'
                }, 2, 'world']
            }
        }

        # assert that without apikey_path_prefix this fails/returns None
        assert GearInfo.load_from_file(configs, DummyGearConfigs) is None

        # assert that without test_int this still fails/returns None
        configs['configs']['apikey_path_prefix'] = '/test/dummy/gearbot'
        assert GearInfo.load_from_file(configs, DummyGearConfigs) is None

        # now make sure that this passes
        configs['configs']['test_int'] = 1
        result = GearInfo.load_from_file(copy.deepcopy(configs),
                                         DummyGearConfigs)
        assert result is not None

        # however output will not be exactly the same, since test_optional
        # was not explicitly passed; test the behavior is as expected
        assert result.configs.test_optional == 'optional'
        assert result.model_dump() != configs
        configs['configs']['test_optional'] = 'optional'
        assert result.model_dump() == configs
