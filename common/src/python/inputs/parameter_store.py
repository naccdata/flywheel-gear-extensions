"""Module for getting proxy object for AWS SSM parameter store object."""
from typing import Optional

from inputs.environment import get_environment_variable
from ssm_parameter_store import EC2ParameterStore


def get_parameter_store() -> Optional[EC2ParameterStore]:
    """Gets a proxy object for the parameter store if AWS credentials are set.
    Expects AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, and AWS_DEFAULT_REGION.

    Returns:
        parameter store object if credentials are valid, and None otherwise
    """
    secret_key = get_environment_variable('AWS_SECRET_ACCESS_KEY')
    access_id = get_environment_variable('AWS_ACCESS_KEY_ID')
    region = get_environment_variable('AWS_DEFAULT_REGION')
    if not secret_key or not access_id or not region:
        return None

    return EC2ParameterStore(aws_access_key_id=access_id,
                             aws_secret_access_key=secret_key,
                             region_name=region)
