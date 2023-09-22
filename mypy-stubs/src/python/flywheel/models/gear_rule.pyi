from typing import List

from .fixed_input import FixedInput
from .gear_rule_condition import GearRuleCondition


class GearRule:

    def __init__(self, project_id: str, gear_id: str, role_id: str, name: str,
                 config: object, fixed_inputs: List[FixedInput],
                 auto_update: bool, any: List[GearRuleCondition],
                 _not: List[GearRuleCondition], all: List[GearRuleCondition],
                 disabled: bool, compute_provider_id: str,
                 triggering_input: str) -> None:
        ...

    @property
    def id(self) -> str:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def project_id(self) -> str:
        ...

    @property
    def gear_id(self) -> str:
        ...

    @property
    def role_id(self) -> str:
        ...

    @property
    def config(self) -> object:
        ...

    @property
    def fixed_inputs(self) -> List[FixedInput]:
        ...

    @property
    def auto_update(self) -> bool:
        ...

    @property
    def any(self) -> List[GearRuleCondition]:
        ...

    @property
    def _not(self) -> List[GearRuleCondition]:
        ...

    @property
    def all(self) -> List[GearRuleCondition]:
        ...

    @property
    def disabled(self) -> bool:
        ...

    @property
    def compute_provider_id(self) -> str:
        ...

    @property
    def triggering_input(self) -> str:
        ...
