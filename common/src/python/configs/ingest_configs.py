"""Form ingest configurations."""

from typing import Dict, List, Optional

from keys.keys import DefaultValues
from pydantic import BaseModel, RootModel


class OptionalFormsConfigs(RootModel):
    root: Dict[str, Dict[str, List[str]]]

    def get_optional_forms(self, version: str,
                           packet: str) -> Optional[List[str]]:
        """Get the list of optional forms for the specified version and packet.

        Args:
            version: form version
            packet: packet code

        Returns:
            Optional[List[str]]: List of optional form names if found
        """
        if not self.root:
            return None

        version_configs = self.root.get(version, {})
        return version_configs.get(packet)


class SupplementModuleConfigs(BaseModel):
    label: str
    date_field: str
    version: Optional[str] = None
    exact_match: Optional[bool] = True


class ModuleConfigs(BaseModel):
    initial_packets: List[str]
    followup_packets: List[str]
    versions: List[str]
    date_field: str
    legacy_module: Optional[str] = None
    legacy_date: Optional[str] = None
    supplement_module: Optional[SupplementModuleConfigs] = None
    optional_forms: Optional[OptionalFormsConfigs] = None


class FormProjectConfigs(BaseModel):
    primary_key: str
    accepted_modules: List[str]
    legacy_project_label: Optional[str] = DefaultValues.LEGACY_PRJ_LABEL
    module_configs: Dict[str, ModuleConfigs]
