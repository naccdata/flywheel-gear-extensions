"""Tests the GearInfo and GearConfigs pydantic classes."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from gear_execution.gear_trigger import CredentialGearConfigs, GearInfo

TEST_FILES_DIR = Path(__file__).parent.resolve() / "data"


class DummyGearConfigs(CredentialGearConfigs):
    test_str: str
    test_int: int
    test_list: List[Any]
    test_optional: Optional[str] = "optional"


class TestGearInfo:
    """Tests the GearInfo and GearConfigs pydantic classes."""

    def test_basic_configs(self):
        """Test a basic create with default GearConfigs class."""

        # assert that when empty fails/returns None
        assert GearInfo.load_from_file(str(TEST_FILES_DIR / "empty-file.json")) is None

        assert GearInfo.load_from_file(str(TEST_FILES_DIR / "no-configs.json")) is None
        result = GearInfo.load_from_file(str(TEST_FILES_DIR / "empty-configs.json"))

        assert result is not None
        assert result.model_dump() == {
            "gear_name": "empty-configs",
            "configs": {},
            "inputs": None,
        }

    def test_credential_gear_configs(self):
        """Test credential gear config class."""

        # assert without apikey_path_prefix fails/returns None
        assert (
            GearInfo.load_from_file(
                str(TEST_FILES_DIR / "empty-configs.json"), CredentialGearConfigs
            )
            is None
        )

        # assert valid credentials gear configs
        result = GearInfo.load_from_file(
            str(TEST_FILES_DIR / "basic-configs.json"), CredentialGearConfigs
        )

        assert result is not None
        assert result.model_dump() == {
            "gear_name": "basic-configs",
            "configs": {"apikey_path_prefix": "/test/dummy/gearbot"},
            "inputs": None,
        }

    def test_custom_configs(self):
        """Test a create with custom GearConfigs class."""
        # assert that without apikey_path_prefix this fails/returns None
        assert (
            GearInfo.load_from_file(
                str(TEST_FILES_DIR / "custom-configs-invalid.json"), DummyGearConfigs
            )
            is None
        )

        # assert that without test_int this still fails/returns None
        assert (
            GearInfo.load_from_file(
                str(TEST_FILES_DIR / "custom-configs-invalid-2.json"), DummyGearConfigs
            )
            is None
        )

        # now make sure that this passes
        result = GearInfo.load_from_file(
            str(TEST_FILES_DIR / "custom-configs.json"), DummyGearConfigs
        )
        assert result is not None

        # however output will not be exactly the same, since test_optional
        # was not explicitly passed; test the behavior is as expected
        configs: Dict[str, Any] = {
            "gear_name": "custom-configs",
            "configs": {
                "test_str": "hello",
                "test_int": 1,
                "test_list": [{"key": "value"}, 2, "world"],
                "apikey_path_prefix": "/test/dummy/gearbot",
            },
        }

        assert result.configs.test_optional == "optional"
        assert result.model_dump() != configs
        configs["configs"]["test_optional"] = "optional"
        configs["inputs"] = None
        assert result.model_dump() == configs

    def test_config_with_input_info(self):
        """Test a custom GearConfigs class with input info."""
        # assert that config with invalid input returns None
        assert (
            GearInfo.load_from_file(
                str(TEST_FILES_DIR / "custom-configs-with-invalid-input.json"),
                DummyGearConfigs,
            )
            is None
        )

        # now make sure that valid input passes
        result = GearInfo.load_from_file(
            str(TEST_FILES_DIR / "custom-configs-with-valid-input.json"),
            DummyGearConfigs,
        )
        assert result is not None

        # however output will not be exactly the same, as optional configs and inputs
        # were not explicitly passed; test the behavior is as expected
        configs: Dict[str, Any] = {
            "gear_name": "custom-configs",
            "inputs": [
                {"label": "input_file1", "file_locator": "matched"},
                {
                    "label": "input_file2",
                    "file_locator": "module",
                    "file_name": "${module}-schema.json",
                },
            ],
            "configs": {
                "test_str": "hello",
                "test_int": 1,
                "test_list": [{"key": "value"}, 2, "world"],
                "apikey_path_prefix": "/test/dummy/gearbot",
            },
        }

        assert result.configs.test_optional == "optional"
        assert not result.inputs[0].file_name
        assert result.model_dump() != configs
        configs["configs"]["test_optional"] = "optional"
        configs["inputs"][0]["file_name"] = None
        assert result.model_dump() == configs
