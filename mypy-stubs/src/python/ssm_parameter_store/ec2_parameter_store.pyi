from typing import Dict, Any


class EC2ParameterStore:

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str,
                 region_name: str) -> None:
        ...

    def get_parameter(self, parameter_name: str,
                      decrypt: bool) -> Dict[str, str]:
        ...

    def get_parameters_by_path(self,
                               path: str,
                               decrypt: bool = True,
                               recursive: bool = True,
                               strip_path: bool = True) -> Dict[str, str]:
        ...

    def get_parameters_with_hierarchy(
            self,
            path: str,
            decrypt: bool = True,
            strip_path: bool = True) -> Dict[str, Any]:
        ...

    ...
