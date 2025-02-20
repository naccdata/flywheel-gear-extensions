from typing import List

from .fixed_input import FixedInput
from .gear_rule_condition import GearRuleCondition
from .job_priority import JobPriority


class GearRuleInput:

    def __init__(self, project_id: str, gear_id: str, role_id: str, name: str,
                 config: object, fixed_inputs: List[FixedInput],
                 auto_update: bool, any: List[GearRuleCondition],
                 _not: List[GearRuleCondition], all: List[GearRuleCondition],
                 disabled: bool, compute_provider_id: str,
                 triggering_input: str, priority: JobPriority) -> None:
        ...

    @property
    def name(self) -> str:
        ...
