"""Utility for getting the FW API key."""

from typing import Optional

from inputs.environment import get_environment_variable
from inputs.parameter_store import get_parameter_store
from ssm_parameter_store import EC2ParameterStore  # type: ignore


def get_api_key(
        parameter_store: Optional[EC2ParameterStore] = None) -> Optional[str]:
    """Get the Flywheel API key from environment.

    Uses FW_API_KEY if set.
    Otherwise, pulls from parameter store if AWS credentials are given in
    AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, and AWS_DEFAULT_REGION.

    Args:
      parameter_store: a parameter store proxy object

    Returns:
        the API Key if defined locally or in parameter store. None, otherwise.
    """
    api_key = get_environment_variable('FW_API_KEY')
    if api_key:
        return api_key

    if not parameter_store:
        parameter_store = get_parameter_store()

    if not parameter_store:
        return None

    parameter_name = '/prod/flywheel/gearbot/apikey'
    parameter = parameter_store.get_parameter(parameter_name, decrypt=True)
    return parameter.get(parameter_name)
