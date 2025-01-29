"""Form ingest configurations."""

from typing import Dict, List, Optional

from keys.keys import DefaultValues
from pydantic import BaseModel


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


class FormProjectConfigs(BaseModel):
    primary_key: str
    accepted_modules: List[str]
    legacy_project_label: Optional[str] = DefaultValues.LEGACY_PRJ_LABEL
    module_configs: Dict[str, ModuleConfigs]
