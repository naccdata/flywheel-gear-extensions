"""Models for executing the dbt-runner."""

from typing import Dict

from pydantic import BaseModel, ValidationError, field_validator
from storage.storage import StorageManager


class StorageConfigs(BaseModel):
    """Model to keep track of DBT storage configs."""

    storage_label: str
    output_prefix: str

    @field_validator("output_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        """Ensure prefixes have no trailing backslash."""
        stripped_value = value.rstrip("/")
        if not stripped_value:
            raise ValidationError(f"Prefix cannot be empty: {value}")

        return stripped_value

    def verify_access(self, storage_manager: StorageManager) -> None:
        """Verify the prefix is accessible."""
        storage_manager.verify_access(None)


class SingleStorageConfigs(StorageConfigs):
    """For when the source data comes from a singular source."""

    source_prefix: str

    @field_validator("source_prefix")
    @classmethod
    def validate_source_prefix(cls, value: str) -> str:
        return cls.validate_prefix(value)

    def verify_access(self, storage_manager: StorageManager) -> None:
        """Verify the prefix is accessible."""
        storage_manager.verify_access(self.source_prefix)


class MultiStorageConfigs(StorageConfigs):
    """For when the source data comes from an aggregation of sources."""

    # maps center to source prefix
    source_prefixes: Dict[str, str]

    @field_validator("source_prefix")
    @classmethod
    def validate_prefixes(cls, value: Dict[str, str]) -> Dict[str, str]:
        return {k: cls.validate_prefix(v) for k, v in value.items()}

    def verify_access(self, storage_manager: StorageManager):
        """Verify all prefixes are accessible."""
        for x in self.source_prefixes.values():
            storage_manager.verify_access(x)
