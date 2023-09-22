from typing import Dict


class EC2ParameterStore:

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str,
                 region_name: str) -> None:
        ...

    def get_parameter(self, parameter_name: str,
                      decrypt: bool) -> Dict[str, str]:
        ...

    ...
