"""Tests loading and substituting the soft-copy gear configs."""

from pathlib import Path

import pytest

from gear_execution.gear_execution import GearExecutionError
from gear_execution.gear_trigger import GearInfo, substitute_gear_configs
from participant_transfer_app.copy import SoftCopyGearConfigs

TEST_FILES_DIR = Path(__file__).parent.resolve() / "data"


def load(filename: str):
    """Loads the named test configs file as soft-copy gear info."""
    return GearInfo.load_from_file(
        str(TEST_FILES_DIR / filename), configs_class=SoftCopyGearConfigs
    )


class TestSoftCopyGearConfigs:
    """Tests the SoftCopyGearConfigs model."""

    def test_valid_configs(self):
        """Test that hyphenated keys populate the aliased fields."""

        result = load("soft-copy-configs.json")

        assert result is not None
        assert result.gear_name == "soft-copy"
        assert result.configs.include_filter == "subject.label={{subject}}"
        assert result.configs.target_project == "{{target}}"
        assert result.configs.duplicate_strategy == "replace"
        assert result.configs.debug is False

    def test_extra_configs_preserved(self):
        """Test that soft-copy configs not in the model are passed through."""

        result = load("soft-copy-configs-extra.json")

        assert result is not None
        assert result.configs.model_dump(by_alias=True) == {
            "debug": False,
            "duplicate-strategy": "skip",
            "include-filter": "subject.label={{subject}}",
            "target-project": "{{target}}",
            "exclude-filter": "acquisition.label=scratch",
        }

    def test_missing_include_filter(self):
        """Test that a missing required config fails to load."""

        assert load("soft-copy-configs-missing-filter.json") is None

    def test_missing_subject_placeholder(self):
        """Test that an include-filter without {{subject}} fails to load."""

        assert load("soft-copy-configs-no-placeholder.json") is None

    def test_missing_target_placeholder(self):
        """Test that a target-project without {{target}} fails to load."""

        assert load("soft-copy-configs-no-target-placeholder.json") is None


class TestSubstituteGearConfigs:
    """Tests substituting placeholders in the soft-copy gear configs."""

    def test_substitution(self):
        """Test that embedded placeholders are substituted."""

        gear_info = load("soft-copy-configs.json")
        assert gear_info is not None

        assert substitute_gear_configs(
            gear_info.configs, subject="NACC000000", target="project-id"
        ) == {
            "debug": False,
            "duplicate-strategy": "replace",
            "include-filter": "subject.label=NACC000000",
            "target-project": "project-id",
        }

    def test_missing_substitution_value(self):
        """Test that a placeholder without a value raises an error."""

        gear_info = load("soft-copy-configs.json")
        assert gear_info is not None

        with pytest.raises(GearExecutionError, match="subject"):
            substitute_gear_configs(gear_info.configs, target="project-id")
